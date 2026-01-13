##人才的分页查询模块
from fastapi import APIRouter,HTTPException,Depends

router3 = APIRouter()

from pydantic import BaseModel
from typing import Optional
from datetime import date
from config import db_config
import pymysql
from fastapi import Depends,Query



class TalentCondition(BaseModel):
    candidate_name:Optional[str] = None
    major:Optional[str] = None
    school:Optional[str] = None
    select_day:Optional[date] = None

COMPUTER_MAJOR_MAPPING = {   #这里做一个专业关联映射，前端设定的专业能把所有相关的近义词专业都关联到。
    # 核心关键词：输入“计算机”时匹配的所有核心专业
    "计算机": [
        "计算机", "计算机科学与技术", "信息安全", "网络空间安全",
        "软件工程", "网络工程", "大数据", "数据科学与大数据技术",
        "人工智能", "智能科学与技术", "物联网工程", "数字媒体技术",'电子信息工程'
    ],
    "信息安全": ['计算机','网络工程',"信息安全", "网络空间安全", "网络安全"],
    "软件工程": ['计算机',"软件工程"],
    "大数据": ["大数据", "数据科学"],
    "人工智能": ["人工智能", "智能科学与技术",'计算机'],
    '网络安全':['计算机','网络工程',"信息安全", "网络空间安全", "网络安全"],
    '土木':['土木工程','项目管理','工程造价','建筑工程'],
    '土木工程':['土木工程','项目管理','工程造价','建筑工程']
}

import re
def _split_list_param(v: str) -> list[str]:
    """
    支持：'a,b' / 'a b' / 'a, b' / 'a  b'
    """
    if not v:
        return []
    return [x for x in re.split(r"[,\s]+", v.strip()) if x]

@router3.get('/talent_list',summary='满足条件的人才分页查询')
async def talent_list(condition:TalentCondition=Depends(),      #依赖注入使得get方法能用请求体参数,这里是查询参数形式
    page: int = Query(1, ge=1),
    page_size:int = Query(10, ge=1, le=100),
    and_keywords: str | None = Query(None, description="and逻辑的关键词（逗号分隔：如candidate_name,major,school,select_day）"),
    or_keywords: str | None = Query(None, description="or逻辑的关键词")):
    where = []
    params = []
    conn = pymysql.connect(**db_config,cursorclass=pymysql.cursors.DictCursor)
    cursor = conn.cursor()
    and_keywords = _split_list_param(and_keywords) #['candidate_name','major','school','select_day']
    or_keywords = _split_list_param(or_keywords)   #['candidate_name','major','school','select_day']

    condition = condition.model_dump(exclude_none=True) #请求体转为字典

    try:
        if and_keywords:
            and_conditions = []  #['candidate_name like %s','major like %s']
            for _ in and_keywords:
                if _ == 'school':
                    and_conditions.append('bachelor_school like %s or graduate_school like %s')
                    params.append(f'%{condition.get('school')}%')
                    params.append(f'%{condition.get('school')}%')
                else:
                    and_conditions.append(f'{_} like %s')
                    v = condition.get(_)
                    params.append(f'%{v}%')
            if len(and_conditions) == 1:
                where.append(and_conditions[0])
            if len(and_conditions) >= 2:
                where.append(f"({' AND '.join(and_conditions)})")        #['candidate_name like %s AND major like %s']


        if or_keywords:
            or_conditions = []    #['school like %s','select_day like %s']
            for _ in or_keywords:
                if _ == 'school':
                    or_conditions.append('bachelor_school like %s or graduate_school like %s')
                    params.append(f'%{condition.get('school')}%')
                    params.append(f'%{condition.get('school')}%')
                else:
                    or_conditions.append(f"{_} LIKE %s")
                    v = condition.get(_)
                    params.append(f'%{v}%')
            if len(or_conditions) == 1:
                where.append(or_conditions[0])
            if len(or_conditions) >= 2:
                where.append(f"({' or '.join(or_conditions)})")          #['candidate_name like %s AND major like %s','school like %s OR select_day like %s]


        if len(where) >= 2:
            where_sql = ' OR '.join(where)
        else:
            where_sql = where[0] if len(where) == 1 else '1=1'
        offset = (page - 1) * page_size
        complete_sql = f'select * from talent_info_table where {where_sql} LIMIT %s OFFSET %s'
        params.append(page_size)
        params.append(offset)
        cursor.execute(complete_sql, params)
        data = cursor.fetchall()
        if len(data) >= 1:
            cursor.close()
            conn.close()
            return data
        else:
            raise HTTPException(status_code=400,detail='未找到符合您要求的候选人才')
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))