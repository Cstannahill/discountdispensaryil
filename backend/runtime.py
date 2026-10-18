"""Worker resource configuration shared by API ingestion and diagnostic scans."""
import os
import threading
import hashlib
from pathlib import Path

_root=Path(__file__).parent
# Include executable browser and Flight parsers in each worker's source revision.
_sources=[_root/name for name in ('runtime.py','service.py','storage.py','domain.py','discovery.py','directory.py','adapters.py','locators.py','site_discovery.py','documents.py','flight.py','network.py','browser_render.py','browser_worker.cjs','browser_locations.cjs','browser_proxy.py')]+sorted((_root/'providers').glob('*.py'))
PIPELINE_VERSION='regional-pipeline-2.'+hashlib.sha256(b''.join(source.read_bytes() for source in _sources)).hexdigest()[:10]


class PipelineInterrupted(RuntimeError):
    pass


def configure_worker_stack():
    # Windows' default worker stack was reproduced crashing inside Python
    # 3.13.3's legacy HTML tag regex during real retailer parsing. The same
    # checkpointed batch passed with an 8 MiB worker stack. Set before spawning
    # workers; this reserves address space rather than committing it all.
    if os.name=='nt' and threading.stack_size()<8*1024*1024:
        threading.stack_size(8*1024*1024)
