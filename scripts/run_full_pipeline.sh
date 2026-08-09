#!/bin/bash
# 爬取完成后的全量数据处理管线（在 crawl --bfs 结束后运行）
set -e
cd "$(dirname "$0")/.."

echo "== 1/9 维度重建（从 profiles_raw）"
python3 scripts/build_maps_from_raw.py
echo "== 2/9 name 兜底（新节点批量 API）"
python3 scripts/fetch_dimension.py --field=name
echo "== 3/9 country 兜底"
python3 scripts/fetch_dimension.py --field=country
echo "== 4/9 team 兜底"
python3 scripts/fetch_dimension.py --field=team
echo "== 5/9 stats 兜底（仅批量阶段）"
python3 scripts/fetch_dimension.py --field=stats --skip-b
echo "== 6/9 profile_map 精选分析层"
python3 scripts/build_profile_map.py
echo "== 7/9 重建图（外部节点入图）"
python3 scripts/merge_lists_into_graph.py
echo "== 8/9 前端数据"
python3 scripts/build_web_profile_data.py
python3 scripts/generate_web_data.py
echo "== 9/9 自检"
python3 scripts/selfcheck.py
echo "PIPELINE DONE"
