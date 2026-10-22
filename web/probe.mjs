import {neon} from '@neondatabase/serverless';
import fs from 'fs';
const url=fs.readFileSync('.env.local','utf8').split('=').slice(1).join('=').trim().replace(/^['"]|['"]$/g,'');
const sql=neon(url);
console.log(await sql.query(`select license_type,status,count(*) from live_endpoints group by 1,2 order by 1,2`));
console.log(await sql.query(`select (payload_json::jsonb->>'completeness') c,(payload_json::jsonb->>'eligible') e,count(*) from live_offers group by 1,2`));
console.log(await sql.query(`select distinct payload_json::jsonb->>'promo' p from live_offers`));
console.log(await sql.query(`select pg_typeof(radius_miles) from live_regions limit 1`));
