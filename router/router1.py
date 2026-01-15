import json
import re
from typing import Optional, List, Any

import pymysql
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from config import db_config
router1 = APIRouter()



class ConditionBody(BaseModel):
    status: Optional[int] = Field(1)
    prompt:Optional[str] = Field("""设定具体的筛选条件""")
    format_prompt:Optional[str] = Field("""
    你负责从简历中提取候选人的核心信息，返回格式（每行一个字段，顺序不变）,如果无该信息就填null：
    姓名:xxx
    年龄:xxx
    联系方式:xxx
    专业:xxx 本科和硕士博士专业不一样的话用逗号连接
    技能:xxx 多个技能用逗号连接
    学历:xxx 写专科/本科/硕士/博士
    本科毕业院校：xxx
    本科学校水平:xxx 国内高校写985211，如果既是985又是211就写985211，只是211就写211，双非就为null，海外高校写qs排名
    研究生毕业院校:xxx
    研究生毕业学校水平:xxx 国内高校写985211，如果既是985又是211就写985211，只是211就写211，双非就为null，海外高校写qs排名
    是否工科:是或否
    """)
    is_deleted: Optional[int] = Field(0)



def _get_connection():
    return pymysql.connect(**db_config, cursorclass=pymysql.cursors.DictCursor)



@router1.post('/add_filter_condition',summary='新增筛选条件')
async def add_filter_condition(req: ConditionBody):
    conn = _get_connection()
    cursor = conn.cursor()

    try:
        prompt = req.prompt
        format_prompt = req.format_prompt
        # 2) 插入
        sql = """
        INSERT INTO filter_condition (prompt,format_prompt)
        VALUES (%s,%s)
        """
        cursor.execute(sql, (prompt,format_prompt)) #("""INSERT INTO filter_condition (condition_json,prompt,is_deleted)VALUES (%s, 0)""",condition_json_str)
        conn.commit()

        new_filter_condition_id = cursor.lastrowid
        return {"msg": "ok", "id": new_filter_condition_id}

    except pymysql.MySQLError as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        cursor.close()
        conn.close() #try模块中有return也会执行finally


@router1.get("/list_filter_condition_summary", summary="筛选条件简介列表")
async def list_filter_condition_summary():
    conn = _get_connection()
    cursor = conn.cursor()
    try:
        sql = """
        SELECT id,prompt,status,is_deleted
        FROM filter_condition
        ORDER BY id DESC
        """


        cursor.execute(sql)
        rows = cursor.fetchall()

        return {"total": len(rows), "list": rows}

    except pymysql.MySQLError as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()





class UpdateFilterConditionReq(BaseModel):
    id: int = Field(..., gt=0)
    prompt:Optional[str] = Field(None)
    format_prompt:Optional[str] = Field(None)
    is_deleted:Optional[int] = Field(None, description='在这个接口也可以做逻辑删除')
    status:Optional[int] = Field(1, ge=0)

@router1.put("/update_filter_condition", summary="更新筛选条件")
async def update_filter_condition(req: UpdateFilterConditionReq):
    conn = _get_connection()
    cursor = conn.cursor()
    total_affected = 0
    try:
        if req.prompt is not None and req.prompt != 'string':
            cursor.execute(
                """
                SELECT prompt
                FROM filter_condition
                WHERE id=%s AND is_deleted=0
                """,
                (req.id,))
            row = cursor.fetchone() #前面定义了cursor的fetch返回字典

            if not row:
                raise HTTPException(status_code=404, detail="记录不存在或已删除")

            cursor.execute(
                """
                UPDATE filter_condition
                SET prompt=%s
                WHERE id=%s AND is_deleted=0
                """,
                (req.prompt,req.id))  # 占位符+绑定参数      #MySQL 执行UPDATE时，即使WHERE条件匹配不到任何记录，也不会报错，只是 “影响行数为 0”。
            total_affected += cursor.rowcount

        if req.format_prompt and req.format_prompt != 'string':
            cursor.execute(
                """
                SELECT prompt
                FROM filter_condition
                WHERE id=%s AND is_deleted=0
                """,
                (req.id,))
            row = cursor.fetchone()  # 前面定义了cursor的fetch返回字典

            if not row:
                raise HTTPException(status_code=404, detail="记录不存在或已删除")

            cursor.execute(
                """
                UPDATE filter_condition
                SET format_prompt=%s
                WHERE id=%s AND is_deleted=0
                """,
                (req.format_prompt, req.id))  # 占位符+绑定参数      #MySQL 执行UPDATE时，即使WHERE条件匹配不到任何记录，也不会报错，只是 “影响行数为 0”。
            total_affected += cursor.rowcount
        if req.status==0:
            cursor.execute(
                """
                UPDATE filter_condition
                SET status=0
                WHERE id=%s AND is_deleted=0
                """,
                (req.id,))  # 占位符+绑定参数      #MySQL 执行UPDATE时，即使WHERE条件匹配不到任何记录，也不会报错，只是 “影响行数为 0”。
            total_affected += cursor.rowcount
        if req.status==1:
            cursor.execute(
                """
                UPDATE filter_condition
                SET status=1
                WHERE id=%s AND is_deleted=0
                """,
                (req.id,))  # 占位符+绑定参数      #MySQL 执行UPDATE时，即使WHERE条件匹配不到任何记录，也不会报错，只是 “影响行数为 0”。
            total_affected += cursor.rowcount
        if req.is_deleted == 1:
            cursor.execute('update filter_condition set is_deleted=1 where id = %s and is_deleted=0',req.id)
            total_affected += cursor.rowcount
        if total_affected == 0:
            raise HTTPException(status_code=404, detail="记录不存在或已删除")
        conn.commit()
        return {"msg": "ok"}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@router1.delete("/delete_filter_condition", summary="删除筛选条件（逻辑删除）")
async def delete_filter_condition(id: int = Query(..., gt=0)):
    conn = _get_connection()
    cursor = conn.cursor()
    try:
        sql = """
        UPDATE filter_condition
        SET is_deleted=1
        WHERE id=%s AND is_deleted=0
        """
        cursor.execute(sql, (id,))
        conn.commit()

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="记录不存在或已删除")

        return {"msg": "ok"}

    except pymysql.MySQLError as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()



def _split_list_param(v: str | None) -> list[str]:
    """
    支持：'a,b' / 'a b' / 'a, b' / 'a  b'
    """
    if not v:
        return []
    return [x for x in re.split(r"[,，\s]+", v.strip()) if x]


class StatusesAndPages(BaseModel):
    page:int = Field(1, ge=1)
    page_size:int = Field(10, ge=0,le=100)

class FilterConditionQuery(BaseModel):
    statuses: Optional[str] = Field(None, description="状态筛选（逗号分隔：如0,1）")
    and_keywords: Optional[str] = Field(None, description="AND关键词（逗号分隔）")
    or_keywords: Optional[str] = Field(None, description="OR关键词（逗号分隔）")

from fastapi import Depends
@router1.get("/list_filter_condition", summary="分页查询筛选条件（支持多条件AND/OR组合）")
async def list_filter_condition(paging: StatusesAndPages = Depends(),
                                filters: FilterConditionQuery = Depends()
):
    conn = _get_connection()
    cursor = conn.cursor()
    try:
        where = ["is_deleted=0"]
        params: list = []
        statuses = filters.statuses
        and_keywords = filters.and_keywords #'本科，985'
        or_keywords = filters.or_keywords

        # 1. 状态筛选（IN）
        if statuses:
            status_list = [int(s) for s in _split_list_param(statuses)]
            where.append(f"status IN ({','.join(['%s']*len(status_list))})")
            params.extend(status_list)

        # 3. AND关键词：必须同时包含所有关键词
        and_list = _split_list_param(and_keywords)   #['本科','985']
        if and_list:
            and_conditions = " AND ".join(["LOWER(prompt) LIKE %s"] * len(and_list)) #就算只有一个元素，join会直接返回这个元素不连接，不报错
            where.append(f"({and_conditions})")
            params.extend([f"%{kw.lower()}%" for kw in and_list])

        # 4. OR关键词：至少包含一个关键词
        or_list = _split_list_param(or_keywords)
        if or_list:
            or_conditions = " OR ".join(["LOWER(prompt) LIKE %s"] * len(or_list))
            where.append(f"({or_conditions})")
            params.extend([f"%{kw.lower()}%" for kw in or_list])

        where_sql = " AND ".join(where) if where else "1=1"

        # 5. 统计总数
        cursor.execute(f"SELECT COUNT(*) AS cnt FROM filter_condition WHERE {where_sql}", params)
        count_result = cursor.fetchone()
        total = count_result["cnt"] if (count_result and count_result.get("cnt")) else 0
        # 6. 分页查询数据
        offset = (paging.page - 1) * paging.page_size
        cursor.execute(f"""
        SELECT id, prompt,format_prompt,status, is_deleted, created_at, updated_at
        FROM filter_condition
        WHERE {where_sql}
        ORDER BY id DESC
        LIMIT %s OFFSET %s
        """, params + [paging.page_size, offset])
        rows = cursor.fetchall()

        return {
            "total": total,
            "page": paging.page,
            "page_size": paging.page_size,
            "list": rows
        }
    except pymysql.MySQLError as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
