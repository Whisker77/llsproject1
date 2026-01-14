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
def _split_list_param(v: str | None) -> list[str]:
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
        allowed_fields = {"candidate_name", "major", "school", "select_day"}
        invalid_and = [field for field in and_keywords if field not in allowed_fields]
        invalid_or = [field for field in or_keywords if field not in allowed_fields]
        if invalid_and or invalid_or:
            invalid_fields = ", ".join(sorted(set(invalid_and + invalid_or))) #按字母顺序排序 例如a<b<c
            raise HTTPException(status_code=400, detail=f"无效字段: {invalid_fields}")

        if and_keywords:
            and_conditions = []  #['candidate_name like %s','major like %s']
            for field in and_keywords:
                if field == 'school':
                    value = condition.get("school")
                    if value is None:
                        raise HTTPException(status_code=400, detail="缺少school筛选值")
                    and_conditions.append('(bachelor_school LIKE %s OR graduate_school LIKE %s)')
                    params.extend([f"%{value}%", f"%{value}%"])
                elif field == "select_day":
                    value = condition.get("select_day")
                    if value is None:
                        raise HTTPException(status_code=400, detail="缺少select_day筛选值")
                    and_conditions.append("select_day = %s")
                    params.append(value)
                else:
                    value = condition.get(field)
                    if value is None:
                        raise HTTPException(status_code=400, detail=f"缺少{field}筛选值")
                    and_conditions.append(f"{field} LIKE %s")
                    params.append(f"%{value}%")
            where.append(f"({' AND '.join(and_conditions)})")

        if or_keywords:
            or_conditions = []    #['school like %s','select_day like %s']
            for field in or_keywords:
                if field == 'school':
                    value = condition.get("school")
                    if value is None:
                        raise HTTPException(status_code=400, detail="缺少school筛选值")
                    or_conditions.append('(bachelor_school LIKE %s OR graduate_school LIKE %s)')
                    params.extend([f"%{value}%", f"%{value}%"])
                elif field == "select_day":
                    value = condition.get("select_day")
                    if value is None:
                        raise HTTPException(status_code=400, detail="缺少select_day筛选值")
                    or_conditions.append("select_day = %s")
                    params.append(value)
                else:
                    value = condition.get(field)
                    if value is None:
                        raise HTTPException(status_code=400, detail=f"缺少{field}筛选值")
                    or_conditions.append(f"{field} LIKE %s")
                    params.append(f"%{value}%")
            where.append(f"({' OR '.join(or_conditions)})")

        where_sql = ' AND '.join(where) if where else '1=1'
        offset = (page - 1) * page_size
        complete_sql = f'select * from talent_info_table where {where_sql} LIMIT %s OFFSET %s'
        params.append(page_size)
        params.append(offset)
        cursor.execute(complete_sql, params)
        data = cursor.fetchall()
        if len(data) >= 1:
            return data
        raise HTTPException(status_code=400,detail='未找到符合您要求的候选人才')
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cursor.close()
        conn.close()
