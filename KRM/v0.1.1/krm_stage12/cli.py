import argparse, json
from .core import Config, load_input, run_stage12, write_bundle

def main():
    p=argparse.ArgumentParser(description="KRM Stage12 v1")
    p.add_argument("input",help="normalized Stage11 JSON")
    p.add_argument("-o","--output",default="KRM_STAGE12_OUTPUT")
    p.add_argument("--config",help="optional Config JSON")
    a=p.parse_args(); cfg=Config(**json.load(open(a.config,encoding="utf-8"))) if a.config else Config()
    result=run_stage12(load_input(a.input),cfg); write_bundle(result,a.output)
    print(json.dumps(result["validation"],ensure_ascii=False,indent=2))
if __name__=="__main__": main()
