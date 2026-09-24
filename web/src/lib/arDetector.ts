/**
 * On-device live viewfinder analysis -- spec 3.D, "AR Live Overlay".
 *
 * What this honestly is
 * ---------------------
 * Two real signals, computed per frame in the browser with no model download:
 *
 *   1. **Barcode**, via the platform `BarcodeDetector` API where available.
 *      That is a genuine decode, not a guess.
 *
 *   2. **Text-region geometry**, via a gradient + morphology pass over a
 *      downscaled frame. This finds *where* printed text blocks are and how
 *      tall they are, which is enough to tell an officer "this panel carries
 *      declarations, and the smallest is around 1.8 mm" before they press the
 *      shutter.
 *
 * What it deliberately does NOT do
 * --------------------------------
 * It does not claim to know which region is the MRP and which is the net
 * quantity. Classifying declarations from a shaky live frame would require a
 * trained on-device model, and guessing would put a confident wrong label in
 * front of an officer. Field identity comes from the server pipeline, where
 * the vision model's reading is cross-checked by OCR before anyone sees it.
 *
 * The value here is capture quality: framing, focus, glare and legibility are
 * all knowable on-device, and catching them at the viewfinder saves a return
 * visit to the shop.
 */

export interface TextRegion {
  x: number;
  y: number;
  width: number;
  height: number;
  /** Estimated cap height in millimetres, when a physical scale is known. */
  heightMm?: number;
}

export interface FrameAnalysis {
  regions: TextRegion[];
  barcode?: { value: string; format: string; box: TextRegion } | null;
  /** Variance of Laplacian; low means the frame is not in focus. */
  sharpness: number;
  /** Fraction of pixels blown out by specular highlight. */
  glareRatio: number;
  brightness: number;
  /** Fraction of the frame the pack appears to occupy. */
  coverage: number;
  advice: string[];
  ready: boolean;
}

// Analysis runs on a downscaled copy: a 1080p frame at 30fps would peg the
// main thread, and text-block geometry survives downscaling perfectly well.
const WORK_WIDTH = 320;

const SHARPNESS_FLOOR = 55;
const GLARE_CEILING = 0.06;
const DARK_FLOOR = 55;
const BRIGHT_CEILING = 215;
const COVERAGE_FLOOR = 0.18;

let barcodeDetector: any = null;
let barcodeUnsupported = false;

export function barcodeSupported(): boolean {
  return typeof window !== 'undefined' && 'BarcodeDetector' in window;
}

async function getBarcodeDetector(): Promise<any> {
  if (barcodeUnsupported) return null;
  if (barcodeDetector) return barcodeDetector;
  if (!barcodeSupported()) {
    barcodeUnsupported = true;
    return null;
  }
  try {
    const Ctor = (window as any).BarcodeDetector;
    const formats: string[] = await Ctor.getSupportedFormats();
    const wanted = ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'code_39']
      .filter((f) => formats.includes(f));
    barcodeDetector = new Ctor(wanted.length ? { formats: wanted } : undefined);
    return barcodeDetector;
  } catch {
    barcodeUnsupported = true;
    return null;
  }
}

/** Analyse one video frame. Cheap enough to run several times a second. */
export async function analyseFrame(
  video: HTMLVideoElement,
  work: HTMLCanvasElement,
  pxPerMm?: number,
): Promise<FrameAnalysis | null> {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!vw || !vh) return null;

  const scale = WORK_WIDTH / vw;
  const w = WORK_WIDTH;
  const h = Math.round(vh * scale);
  work.width = w;
  work.height = h;

  const ctx = work.getContext('2d', { willReadFrequently: true });
  if (!ctx) return null;
  ctx.drawImage(video, 0, 0, w, h);

  const { data } = ctx.getImageData(0, 0, w, h);

  // --- luminance, brightness, glare ---
  const gray = new Float32Array(w * h);
  let sum = 0;
  let blown = 0;
  for (let i = 0, p = 0; i < data.length; i += 4, p += 1) {
    const g = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
    gray[p] = g;
    sum += g;
    if (g >= 250) blown += 1;
  }
  const brightness = sum / gray.length;
  const glareRatio = blown / gray.length;

  // --- sharpness: variance of a 4-neighbour Laplacian ---
  let lapSum = 0;
  let lapSq = 0;
  let lapN = 0;
  for (let y = 1; y < h - 1; y += 1) {
    for (let x = 1; x < w - 1; x += 1) {
      const i = y * w + x;
      const lap = 4 * gray[i] - gray[i - 1] - gray[i + 1] - gray[i - w] - gray[i + w];
      lapSum += lap;
      lapSq += lap * lap;
      lapN += 1;
    }
  }
  const mean = lapSum / lapN;
  const sharpness = lapSq / lapN - mean * mean;

  // --- text regions -------------------------------------------------------
  // Printed text is a dense cluster of short, high-contrast horizontal edges.
  // A horizontal gradient magnitude, thresholded and then dilated along the
  // writing direction, merges characters into words and words into lines --
  // the same morphology the server pipeline uses, in miniature.
  const edges = new Uint8Array(w * h);
  let edgeCount = 0;
  for (let y = 1; y < h - 1; y += 1) {
    for (let x = 1; x < w - 1; x += 1) {
      const i = y * w + x;
      const gx = Math.abs(gray[i + 1] - gray[i - 1]);
      const gy = Math.abs(gray[i + w] - gray[i - w]);
      // Favour vertical strokes: text has many, flat product photography has few.
      if (gx > 26 && gx > gy * 0.7) {
        edges[i] = 1;
        edgeCount += 1;
      }
    }
  }

  const dilated = new Uint8Array(w * h);
  const RUN = Math.max(4, Math.round(w * 0.035));
  for (let y = 0; y < h; y += 1) {
    let run = 0;
    for (let x = 0; x < w; x += 1) {
      const i = y * w + x;
      if (edges[i]) run = RUN;
      if (run > 0) {
        dilated[i] = 1;
        run -= 1;
      }
    }
  }

  const regions = extractRegions(dilated, w, h);
  const coverage = edgeCount / (w * h) > 0 ? estimateCoverage(dilated, w, h) : 0;

  // Map region geometry back to full-frame coordinates.
  const scaled: TextRegion[] = regions.map((r) => ({
    x: r.x / scale,
    y: r.y / scale,
    width: r.width / scale,
    height: r.height / scale,
    heightMm: pxPerMm ? Number(((r.height / scale) / pxPerMm).toFixed(2)) : undefined,
  }));

  // --- barcode ---
  let barcode: FrameAnalysis['barcode'] = null;
  const detector = await getBarcodeDetector();
  if (detector) {
    try {
      const found = await detector.detect(video);
      if (found?.length) {
        const b = found[0];
        barcode = {
          value: String(b.rawValue ?? ''),
          format: String(b.format ?? 'unknown'),
          box: {
            x: b.boundingBox?.x ?? 0,
            y: b.boundingBox?.y ?? 0,
            width: b.boundingBox?.width ?? 0,
            height: b.boundingBox?.height ?? 0,
          },
        };
      }
    } catch {
      /* detection can fail transiently on a frame; next frame will retry */
    }
  }

  // --- capture-quality advice --------------------------------------------
  const advice: string[] = [];
  if (sharpness < SHARPNESS_FLOOR) advice.push('Hold steady — the frame is not sharp yet');
  if (glareRatio > GLARE_CEILING) advice.push('Glare on the pack — tilt away from the light');
  if (brightness < DARK_FLOOR) advice.push('Too dark to read small print');
  else if (brightness > BRIGHT_CEILING) advice.push('Overexposed — move out of direct light');
  if (coverage < COVERAGE_FLOOR) advice.push('Move closer so the pack fills the frame');
  if (!scaled.length) advice.push('No printed text detected — aim at the declaration panel');

  const ready =
    sharpness >= SHARPNESS_FLOOR &&
    glareRatio <= GLARE_CEILING &&
    brightness >= DARK_FLOOR &&
    brightness <= BRIGHT_CEILING &&
    coverage >= COVERAGE_FLOOR &&
    scaled.length > 0;

  return {
    regions: scaled,
    barcode,
    sharpness: Math.round(sharpness),
    glareRatio: Number(glareRatio.toFixed(4)),
    brightness: Math.round(brightness),
    coverage: Number(coverage.toFixed(3)),
    advice,
    ready,
  };
}

/** Connected-component labelling over the dilated edge mask. */
function extractRegions(mask: Uint8Array, w: number, h: number): TextRegion[] {
  const seen = new Uint8Array(w * h);
  const out: TextRegion[] = [];
  const stack: number[] = [];

  for (let start = 0; start < mask.length; start += 1) {
    if (!mask[start] || seen[start]) continue;

    stack.length = 0;
    stack.push(start);
    seen[start] = 1;

    let minX = w;
    let maxX = 0;
    let minY = h;
    let maxY = 0;
    let size = 0;

    while (stack.length) {
      const i = stack.pop()!;
      const x = i % w;
      const y = (i / w) | 0;
      size += 1;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;

      // 4-connectivity is enough here and roughly twice as fast as 8.
      if (x > 0 && mask[i - 1] && !seen[i - 1]) { seen[i - 1] = 1; stack.push(i - 1); }
      if (x < w - 1 && mask[i + 1] && !seen[i + 1]) { seen[i + 1] = 1; stack.push(i + 1); }
      if (y > 0 && mask[i - w] && !seen[i - w]) { seen[i - w] = 1; stack.push(i - w); }
      if (y < h - 1 && mask[i + w] && !seen[i + w]) { seen[i + w] = 1; stack.push(i + w); }
    }

    const bw = maxX - minX + 1;
    const bh = maxY - minY + 1;

    // Keep only things shaped like a line of text: wider than tall, not a
    // hairline, not the whole frame.
    if (bw < w * 0.06) continue;
    if (bh < 3 || bh > h * 0.28) continue;
    if (bw / bh < 1.6) continue;
    if (size < bw * bh * 0.25) continue;

    out.push({ x: minX, y: minY, width: bw, height: bh });
  }

  // Largest first, capped: a HUD with forty boxes on it communicates nothing.
  return out.sort((a, b) => b.width * b.height - a.width * a.height).slice(0, 14);
}

/** Rough share of the frame occupied by the pack, from where text sits. */
function estimateCoverage(mask: Uint8Array, w: number, h: number): number {
  let minX = w;
  let maxX = 0;
  let minY = h;
  let maxY = 0;
  let any = false;
  for (let y = 0; y < h; y += 2) {
    for (let x = 0; x < w; x += 2) {
      if (!mask[y * w + x]) continue;
      any = true;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  }
  if (!any) return 0;
  return ((maxX - minX) * (maxY - minY)) / (w * h);
}

/** Paint the HUD. Colour encodes capture readiness, not field identity. */
export function drawOverlay(
  canvas: HTMLCanvasElement,
  analysis: FrameAnalysis | null,
  displayWidth: number,
  displayHeight: number,
  videoWidth: number,
  videoHeight: number,
): void {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  canvas.width = displayWidth;
  canvas.height = displayHeight;
  ctx.clearRect(0, 0, displayWidth, displayHeight);
  if (!analysis || !videoWidth || !videoHeight) return;

  // The video is object-cover'd, so the overlay must apply the same crop or
  // every box lands in the wrong place.
  const scale = Math.max(displayWidth / videoWidth, displayHeight / videoHeight);
  const offsetX = (displayWidth - videoWidth * scale) / 2;
  const offsetY = (displayHeight - videoHeight * scale) / 2;
  const tx = (x: number) => x * scale + offsetX;
  const ty = (y: number) => y * scale + offsetY;

  const colour = analysis.ready ? '#22c55e' : '#f59e0b';

  ctx.lineWidth = 2;
  ctx.strokeStyle = colour;
  ctx.fillStyle = `${colour}1a`;
  ctx.font = '600 12px system-ui, sans-serif';

  for (const r of analysis.regions) {
    const x = tx(r.x);
    const y = ty(r.y);
    const w = r.width * scale;
    const h = r.height * scale;
    ctx.fillRect(x, y, w, h);
    ctx.strokeRect(x, y, w, h);

    if (r.heightMm) {
      // Rule 11's floor is 1 mm; anything under is worth flagging in the HUD.
      const tooSmall = r.heightMm < 1.0;
      ctx.fillStyle = tooSmall ? '#dc2626' : colour;
      ctx.fillRect(x, y - 16, 52, 15);
      ctx.fillStyle = '#fff';
      ctx.fillText(`${r.heightMm.toFixed(1)} mm`, x + 4, y - 4);
      ctx.fillStyle = `${colour}1a`;
    }
  }

  if (analysis.barcode) {
    const b = analysis.barcode.box;
    ctx.strokeStyle = '#3b82f6';
    ctx.lineWidth = 3;
    ctx.strokeRect(tx(b.x), ty(b.y), b.width * scale, b.height * scale);
    ctx.fillStyle = '#3b82f6';
    ctx.fillRect(tx(b.x), ty(b.y) - 18, 132, 17);
    ctx.fillStyle = '#fff';
    ctx.fillText(analysis.barcode.value.slice(0, 16), tx(b.x) + 5, ty(b.y) - 5);
  }
}
