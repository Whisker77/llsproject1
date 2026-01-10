from fastapi import FastAPI
import uvicorn
from router.router1 import router1
from router.router2 import router2
from router.router3 import router3

app = FastAPI()

app.include_router(router1,tags=['筛选条件表操作接口'])
app.include_router(router2,tags=['简历文件基础信息上传与筛选接口'])
app.include_router(router3,tags=['人才查询接口'])

if __name__ == '__main__':
    uvicorn.run('main:app', host='127.0.0.1', port=8003,reload=True)
