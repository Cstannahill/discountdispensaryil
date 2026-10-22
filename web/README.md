# TerpScout web (Next.js, reads Neon)

Read-only deals app for Vercel. The PC scrapes into SQLite and `scripts/mirror_to_neon.py` mirrors into Neon; this app only reads.

- `DATABASE_URL` (Neon connection string; `NEON_DATABASE_URL` also accepted). Local: `web/.env.local` (git-ignored). Vercel: project env var.
- `npm run dev` / `npm run build` / `npm start`
- `lib/deals.ts` ports `StoreDB.query_offers` to one Postgres query: eligible, active, fresh (12h), grade A and not a price outlier (stamped by the mirror from `backend/matching.py`) unless "include unverified", whole flower unless a grade is chosen, ranked by effective $/g then distance. Counts match the SQLite backend exactly.
- `GET /api/v1/deals` and `/api/v1/regions` mirror the FastAPI shapes (without `data_version` paging checks).
- Regions are the ones the PC has already synced; picking an area never triggers a scrape.
