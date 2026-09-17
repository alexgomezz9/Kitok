from __future__ import annotations
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
import httpx
from .models import ContentItem, MPTTask

TASK_STATE_FAILED=-1
TASK_STATE_COMPLETE=1
TASK_STATE_PROCESSING=4

class MPTError(RuntimeError): pass

class MPTClient:
    def __init__(self, base_url, api_key="", timeout_seconds=30, retry_attempts=4, retry_base_seconds=1.5):
        self.base_url = base_url.rstrip("/")
        self.retry_attempts = retry_attempts
        self.retry_base_seconds = retry_base_seconds
        headers={"User-Agent":"kitok-pipeline/0.1"}
        if api_key: headers["x-api-key"]=api_key
        self.client=httpx.Client(base_url=self.base_url,headers=headers,timeout=timeout_seconds,follow_redirects=True)

    def close(self): self.client.close()

    def _unwrap(self,response):
        try: response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise MPTError(f"MPT HTTP {response.status_code}: {response.text[:1500]}") from e
        try: payload=response.json()
        except ValueError as e: raise MPTError(f"MPT returned non-JSON: {response.text[:1000]}") from e
        if int(payload.get("status",200))>=400:
            raise MPTError(f"MPT API error: {payload}")
        data=payload.get("data",payload)
        if not isinstance(data,dict): raise MPTError(f"Unexpected MPT response: {payload}")
        return data

    def _get_retry(self,url):
        last=None
        for n in range(self.retry_attempts):
            try:
                r=self.client.get(url)
                if r.status_code in {429,500,502,503,504}: raise MPTError(f"Transient HTTP {r.status_code}")
                return r
            except (httpx.HTTPError,MPTError) as e:
                last=e
                if n+1==self.retry_attempts: break
                time.sleep(self.retry_base_seconds*(2**n))
        raise MPTError(f"GET failed after retries: {last}")

    def check(self):
        return self._unwrap(self._get_retry("/api/v1/tasks?page=1&page_size=1"))

    def submit_video(self,item:ContentItem,preset:dict[str,Any])->str:
        payload=dict(preset)
        payload.update(video_subject=item.subject,video_script=item.effective_script,video_terms=item.keywords)
        # Deliberately no automatic POST retry: a timeout could otherwise duplicate a render.
        try: r=self.client.post("/api/v1/videos",json=payload)
        except httpx.HTTPError as e:
            raise MPTError("Submit failed. Check MPT task history before retrying to avoid duplicates.") from e
        data=self._unwrap(r)
        tid=data.get("task_id")
        if not tid: raise MPTError(f"No task_id returned: {data}")
        return str(tid)

    def get_task(self,task_id):
        data=self._unwrap(self._get_retry(f"/api/v1/tasks/{task_id}"))
        return MPTTask(
            task_id=str(data.get("task_id") or task_id),
            state=data.get("state"), progress=data.get("progress"),
            videos=list(data.get("videos") or []),
            error=data.get("error"), failed_stage=data.get("failed_stage"), raw=data
        )

    def artifact_url(self,artifact):
        return artifact if artifact.startswith(("http://","https://")) else urljoin(self.base_url+"/",artifact.lstrip("/"))

    def download_artifact(self,artifact,destination:Path):
        destination.parent.mkdir(parents=True,exist_ok=True)
        tmp=destination.with_suffix(destination.suffix+".part")
        url=self.artifact_url(artifact)
        last=None
        for n in range(self.retry_attempts):
            try:
                with self.client.stream("GET",url) as r:
                    if r.status_code in {429,500,502,503,504}: raise MPTError(f"Transient artifact HTTP {r.status_code}")
                    r.raise_for_status()
                    with tmp.open("wb") as f:
                        for chunk in r.iter_bytes(): f.write(chunk)
                tmp.replace(destination); return destination
            except (httpx.HTTPError,MPTError,OSError) as e:
                last=e; tmp.unlink(missing_ok=True)
                if n+1==self.retry_attempts: break
                time.sleep(self.retry_base_seconds*(2**n))
        raise MPTError(f"Artifact download failed: {last}")
