import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { Icon } from '@/components/icons';
import { Page } from '@/components/motion';
import {
  Card, ComplianceBadge, Empty, ErrorBox, Item, Loading, PageHeader, ScoreRing,
  ScoreScale, Section, Stagger, money,
} from '@/components/ui';
import { api } from '@/store/auth';

const PAGE_SIZE = 24;

/** Hold a control value back from the query key until typing settles. */
function useDebounced<T>(value: T, ms = 350): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setSettled(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return settled;
}

export default function Catalogue() {
  const [search, setSearch] = useState('');
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [page, setPage] = useState(1);
  const debSearch = useDebounced(search);

  const cats = useQuery({ queryKey: ['categories'], queryFn: () => api.categories() });
  const products = useQuery({
    queryKey: ['products', debSearch, flaggedOnly, page],
    queryFn: () => api.products({
      search: debSearch || undefined, flagged_only: flaggedOnly, page, page_size: PAGE_SIZE,
    }),
    // The grid stays put while a new page loads; swapping it for a skeleton on
    // every keystroke makes the list feel like it is fighting the typist.
    placeholderData: keepPreviousData,
  });

  const total = products.data?.total ?? 0;
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <Page className="space-y-8">
      <PageHeader
        eyebrow={<span className="eyebrow">Public record</span>}
        title="Compliance catalogue"
        subtitle="Every commodity that has been inspected, with the record behind its score. Ranked and searchable."
      />

      {/* ------------------------------------------- category standings -- */}
      {cats.data && (
        <Section
          title="Where the categories stand"
          subtitle="Average compliance score across every inspection in that category."
        >
          <Stagger className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {cats.data.categories.slice(0, 9).map((c) => (
              <Item key={c.slug}>
                <Card className="flex items-center gap-3.5 p-3.5">
                  <span className="display w-7 shrink-0 text-center text-xl font-semibold leading-none text-ink-faint">
                    {c.rank}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">{c.name}</p>
                    <p className="nums mt-0.5 text-2xs text-ink-muted">
                      {c.total_inspections} inspection{c.total_inspections === 1 ? '' : 's'} ·{' '}
                      {c.rules_applied} rules applied
                    </p>
                    {c.seasonal_multiplier > 1 && (
                      <p className="mt-1 inline-flex items-center gap-1 text-2xs font-semibold text-warn">
                        <Icon.sparkle size={10} />
                        ×{c.seasonal_multiplier} seasonal risk
                      </p>
                    )}
                  </div>
                  <ComplianceBadge
                    level={c.badge}
                    size="sm"
                    score={c.avg_compliance_score != null ? Math.round(c.avg_compliance_score) : null}
                  />
                </Card>
              </Item>
            ))}
          </Stagger>
        </Section>
      )}

      {/* --------------------------------------------------- products ---- */}
      <Section
        title="Products"
        subtitle={total ? `${total.toLocaleString('en-IN')} on record` : undefined}
        action={
          <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
            <input
              type="checkbox" checked={flaggedOnly}
              onChange={(e) => { setFlaggedOnly(e.target.checked); setPage(1); }}
              className="size-4 rounded border-line-strong accent-[hsl(var(--accent))]"
            />
            Flagged only
          </label>
        }
      >
        <div className="relative">
          <Icon.search
            size={16}
            className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-faint"
          />
          <input
            className="input pl-10"
            value={search}
            placeholder="Search by product name, brand or barcode"
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            aria-label="Search the catalogue"
          />
        </div>

        {products.isLoading ? (
          <Loading rows={3} />
        ) : products.error ? (
          <ErrorBox error={products.error} retry={() => products.refetch()} />
        ) : !products.data?.items.length ? (
          <Empty
            icon="search"
            title="Nothing matches that search"
            hint={
              flaggedOnly
                ? 'No flagged product matches. Clear the filter to search the whole catalogue.'
                : 'Try a brand name, a product name, or a full 13-digit barcode.'
            }
            action={
              flaggedOnly ? (
                <button type="button" className="btn-ghost" onClick={() => setFlaggedOnly(false)}>
                  Clear the flagged filter
                </button>
              ) : undefined
            }
          />
        ) : (
          <>
            <Stagger className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" delay={0.025}>
              {products.data.items.map((p) => (
                <Item key={p.id}>
                  <Link to={p.barcode ? `/catalogue/${p.barcode}` : '#'} className="block h-full">
                    <Card interactive className="flex h-full flex-col p-4">
                      <div className="flex items-start gap-3.5">
                        <ScoreRing score={p.avg_score} size={48} />
                        <div className="min-w-0 flex-1">
                          <p className="truncate font-semibold leading-tight">{p.product_name}</p>
                          <p className="truncate text-2xs text-ink-muted">{p.brand_name}</p>
                          <div className="mt-1.5">
                            <ComplianceBadge level={p.badge_level} size="sm" />
                          </div>
                        </div>
                      </div>

                      <dl className="mt-3.5 flex items-end justify-between gap-3 border-t border-line pt-3">
                        <div>
                          <dt className="eyebrow">MRP</dt>
                          <dd className="nums mt-0.5 font-semibold">{money(p.official_mrp)}</dd>
                        </div>
                        <div className="text-right">
                          <dt className="eyebrow">Net quantity</dt>
                          <dd className="nums mt-0.5 font-semibold">{p.net_quantity ?? '—'}</dd>
                        </div>
                      </dl>

                      {p.violation_count > 0 && (
                        <p className="mt-2.5 flex items-center gap-1.5 text-2xs font-semibold text-bad">
                          <Icon.alert size={11} />
                          {p.violation_count} recorded violation{p.violation_count === 1 ? '' : 's'}
                        </p>
                      )}
                    </Card>
                  </Link>
                </Item>
              ))}
            </Stagger>

            <nav className="flex items-center justify-between gap-3 pt-1" aria-label="Pagination">
              <p className="nums text-sm text-ink-muted">
                Page {page} of {lastPage}
                <span className="text-ink-faint"> · {total.toLocaleString('en-IN')} products</span>
              </p>
              <div className="flex gap-2">
                <button
                  type="button" className="btn-ghost btn-sm" disabled={page === 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  Previous
                </button>
                <button
                  type="button" className="btn-ghost btn-sm" disabled={page >= lastPage}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </button>
              </div>
            </nav>
          </>
        )}
      </Section>

      <ScoreScale />
    </Page>
  );
}
