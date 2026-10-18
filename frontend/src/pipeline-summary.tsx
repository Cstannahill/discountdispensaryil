import { useQuery } from '@tanstack/react-query';
import { api, params, type ID } from './api';
import { Failure, Loading } from './ui';

interface WorkReport { pipeline_version:string; total_stores:number; counts:Record<string,number> }
function validateReport(report:WorkReport):WorkReport {
  const keys=['accepted','extraction_incomplete','source_unresolved','not_attempted_current_pipeline'];
  if (!report || typeof report.pipeline_version!=='string' || !Number.isInteger(report.total_stores) || !report.counts ||
      keys.some(key=>!Number.isInteger(report.counts[key]) || report.counts[key]<0) ||
      keys.reduce((sum,key)=>sum+report.counts[key],0)!==report.total_stores) {
    throw new Error('Pipeline progress response is invalid; retry after the server finishes updating.');
  }
  return report;
}
export function PipelineSummary({regionId}:{regionId:ID}) {
  const query=useQuery({queryKey:['pipeline-report',regionId],queryFn:async()=>validateReport(await api<WorkReport>(`/pipeline/report?${params({region_id:regionId})}`)),retry:false});
  return <section className="glass-card rounded-2xl p-4 space-y-3" aria-label="Regional pipeline work">
    <h2 className="text-sm font-bold">Regional discovery &amp; extraction progress</h2>
    {query.isPending?<Loading/>:query.isError?<Failure error={query.error} retry={()=>void query.refetch()}/>:<>
      <p className="text-xs text-slate-400">Latest work with {query.data.pipeline_version} across {query.data.total_stores} physical locations. Existing accepted menus remain available independently of these attempts.</p>
      <div className="flex flex-wrap gap-2 text-xs">{Object.entries({accepted:'accepted in this pipeline',extraction_incomplete:'menu extraction incomplete',source_unresolved:'source unresolved',not_attempted_current_pipeline:'not yet run with this pipeline'}).map(([key,label])=><span className="badge" key={key}>{query.data.counts[key]??0} {label}</span>)}</div>
      <p className="text-[11px] text-slate-400">Historical failure messages are not a current retry. Website discovery, supported extraction and accepted inventory are separate stages.</p>
    </>}
  </section>;
}
