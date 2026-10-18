import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';

export function useDataRefresh(revision?: string) {
  const client=useQueryClient();
  const previous=useRef<string | undefined>(undefined);
  useEffect(()=>{
    if (!revision) return;
    if (previous.current && previous.current!==revision) {
      void client.invalidateQueries({predicate:query=>query.queryKey[0]!=='health'});
    }
    previous.current=revision;
  },[revision,client]);
}
