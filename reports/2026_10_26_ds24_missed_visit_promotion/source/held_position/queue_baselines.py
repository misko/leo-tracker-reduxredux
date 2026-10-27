"""Share four total position workers across the two fixed DS24 strata."""
from pathlib import Path
from position import HERE,read,write,sha

def main():
    held=read(HERE/'baseline_v3/protocol.json');dev=read(HERE/'development_baseline/protocol.json')
    first_path=HERE/'baseline_v3/first_terminal_seal.json';first=read(first_path)
    assert first['all_terminal'] and not first['denied_paths']
    assert len(first['results'])==1 and first['results'][0]['status'] in ('complete','capped','inference_unavailable')
    for p,h in first['output_sha256'].items():assert sha(p)==h,p
    jobs=held['jobs'][1:]+dev['jobs'];inputs=dict(held['inputs_sha256'],**dev['inputs_sha256'])
    sources=dict(held['sources_sha256'],**dev['sources_sha256'])
    for p in [Path(__file__),first_path,HERE/'baseline_v3/protocol.json',HERE/'development_baseline/protocol.json']:
        sources[str(p)]=sha(p)
    for p,h in dict(sources,**inputs).items():assert sha(p)==h,p
    study=HERE/'baseline_queue'
    write(study/'protocol.json',dict(held,jobs=jobs,cases=held['cases']+dev['cases'],sources_sha256=sources,inputs_sha256=inputs,strata={'held':held['cases'],'development':dev['cases']},controls=dev['controls'],first_attempt_result=first['results'][0],first_attempt_terminal_sha256=sha(first_path),maximum_workers=4,baseline_queue_only=True,primary_candidate_held_for_coherent_handoff=True))
    print(dict(jobs=len(jobs),first_case_status=first['results'][0]['status'],maximum_workers=4,protocol_sha256=sha(study/'protocol.json')),flush=True)

if __name__=='__main__':main()
