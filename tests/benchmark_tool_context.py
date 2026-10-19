"""Schema-size comparison without calling the model. Run per revision."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    sys.path.insert(0,str(args.repo.resolve()))
    from core.router import Router
    from core.tools_registry import tools
    rows=[]
    for label,goal in [('greeting','ola auren'),('open_app','abra o bloco de notas'),
                       ('maximize','maximize o bloco de notas'),
                       ('browser_search','pesquise receitas de lasanha no navegador'),
                       ('youtube_select','abra o YouTube e pesquise receitas de lasanha e clique no video mais relevante')]:
        selected=Router().select_tools(goal,tools)
        rows.append({'scenario':label,'tool_count':len(selected),
                     'schema_chars':len(json.dumps(selected,ensure_ascii=False))})
    print(json.dumps({'mode':'schema_size_only_no_api','scenarios':rows}))


if __name__=='__main__':
    main()
