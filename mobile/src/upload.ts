/**
 * Turning a local photo into something the network layer will actually send.
 *
 * This took three wrong turns, so the constraints are worth stating.
 *
 * React Native's own FormData takes a `{ uri, name, type }` descriptor and lets
 * the native side stream the file off disk. Expo SDK 54+ replaces the global
 * `fetch` with its WinterCG implementation, which builds the multipart body in
 * JavaScript instead. `expo/src/winter/fetch/convertFormData.ts` accepts:
 *
 *   - a string
 *   - something `instanceof Blob`
 *   - an object exposing `bytes()`
 *
 * and throws "Unsupported FormDataPart implementation" on anything else -- the
 * uri descriptor included. Its own comment says so: "`uri` is not supported for
 * React Native's FormData."
 *
 * The obvious next move, reading the file into an ArrayBuffer and wrapping it in
 * `new Blob([buffer])`, also fails: React Native's Blob polyfill refuses to be
 * constructed from an ArrayBuffer or a typed array at all.
 *
 * What works is the third branch. expo-file-system's `File` implements the Blob
 * interface and exposes `bytes()`, so it can be handed to FormData directly --
 * no intermediate copy, no RN Blob, and the read happens inside the converter
 * rather than ahead of it.
 */
import { File as FsFile } from 'expo-file-system';

/** Guess a mime type from the extension the camera produced. */
export function mimeForUri(uri: string): string {
  if (/\.png($|\?)/i.test(uri)) return 'image/png';
  if (/\.webp($|\?)/i.test(uri)) return 'image/webp';
  if (/\.heic($|\?)/i.test(uri)) return 'image/heic';
  return 'image/jpeg';
}

/**
 * A FormData-ready handle on a captured photo.
 *
 * Returned as `Blob` because that is what the shared client's signature asks
 * for and what `File` implements; the cast is the honest description of a real
 * structural match, not a way to silence the compiler.
 */
export function fileForUpload(uri: string): Blob {
  const file = new FsFile(uri);
  if (!file.exists) {
    // A capture whose file has been evicted from the cache is unrecoverable,
    // and saying that is far more useful than a multipart error thrown three
    // layers down.
    throw new Error(
      'The captured photograph is no longer on this device. It may have been '
      + 'cleared from the cache; the inspection will need re-capturing.',
    );
  }
  return file as unknown as Blob;
}
