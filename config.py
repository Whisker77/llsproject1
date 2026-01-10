
from minio import Minio
db_config = {
    'host':'127.0.0.1',
    'port':3306,
    'user':'root',
    'password':'123456',
    'database':'resume',
    'charset':'utf8'
}


minio_client = Minio(
    endpoint="localhost:9100",   # ✅ 一定要带端口
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False
)
