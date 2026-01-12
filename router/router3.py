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
    name:Optional[str] = None
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

@router3.get('/talent_list',summary='满足条件的人才分页查询')
async def talent_list(condition:TalentCondition=Depends(),
    page: int = Query(1, ge=1),
    page_size:int = Query(10, ge=1, le=100)): #依赖注入使得get方法能用请求体参数
    where = []
    params = []
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()
    try:
        if condition.name:
            where.append('candidate_name like %s')
            params.append(f'%{condition.name}%')
        if condition.major:
            related_majors = COMPUTER_MAJOR_MAPPING.get(condition.major, [condition.major])
            # 加非空判断：避免生成空括号
            if related_majors:
                major_conditions = ['major like %s' for _ in related_majors]
                where.append(f'({" or ".join(major_conditions)})')
                for major in related_majors:
                    params.append(f'%{major}%')
        if condition.school:
            where.append('(bachelor_school like %s or graduate_school like %s)')
            params.append(f'%{condition.school}%')
            params.append(f'%{condition.school}%')
        if condition.select_day:
            where.append('select_day = %s')
            params.append(condition.select_day)
        if where:
            where_sql = ' AND '.join(where)
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