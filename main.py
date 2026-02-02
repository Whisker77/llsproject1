from fastapi import FastAPI
import uvicorn
from router.router1 import router1
from router.router2 import router2
from router.router3 import router3

app = FastAPI()

app.include_router(router1,tags=['筛选条件表操作接口'])
app.include_router(router2,tags=['简历文件基础信息上传与筛选入库接口'])
app.include_router(router3,tags=['满足条件的人才查询接口'])

if __name__ == '__main__':
    uvicorn.run('main:app', host='127.0.0.1', port=8003,reload=True)



def main(text: str) -> dict:
  start = text.find("</think>") + 8
  print(f"start:{start}")
  content_after_marker = text[start:]
  print(f"content_after_marker:{content_after_marker.strip()}")
  echarts_content = content_after_marker.strip()
  echarts_start = echarts_content.find("```echarts")
  print(f"echarts_start:{echarts_start}")
  if echarts_start != -1:
    # 截取从"```echarts"开始到最后一个"```"结束的内容
    echarts_content = echarts_content[echarts_start+10:]
    print(f"filter chars from echarts_content:{echarts_content}")
    print(f"filter:{echarts_content}")
  return {
    "result": echarts_content,
  }

