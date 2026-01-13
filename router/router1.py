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
    is_deleted: Optional[int] = Field(0)



def _get_connection():
    return pymysql.connect(**db_config, cursorclass=pymysql.cursors.DictCursor)



@router1.post('/add_filter_condition',summary='新增筛选条件')
async def add_filter_condition(req: ConditionBody):
    conn = _get_connection()
    cursor = conn.cursor()

    try:
        prompt = req.prompt
        # 2) 插入
        sql = """
        INSERT INTO filter_condition (prompt)
        VALUES (%s)
        """
        cursor.execute(sql, (prompt,)) #("""INSERT INTO filter_condition (condition_json,prompt,is_deleted)VALUES (%s, 0)""",condition_json_str)
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
    is_deleted:Optional[int] = Field(None, decription='在这个接口也可以做逻辑删除')
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



def _split_list_param(v: str) -> list[str]:
    """
    支持：'a,b' / 'a b' / 'a, b' / 'a  b'
    """
    return [x for x in re.split(r"[,\s]+", v.strip()) if x]


@router1.get("/list_filter_condition", summary="分页查询筛选条件（支持多条件AND/OR组合）")
async def list_filter_condition(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    # 基础状态筛选
    statuses: str | None = Query(None, description="状态多选项（逗号分隔：如0,1）"),
    # 筛选条件（prompt模糊匹配）
    and_keywords: str | None = Query(None, description="and逻辑的关键词（逗号分隔：如本科,计算机）"),
    or_keywords: str | None = Query(None, description="or逻辑的关键词（逗号分隔：如985,211）")
):
    conn = _get_connection()
    cursor = conn.cursor()
    try:
        where = ["is_deleted=0"]  # 基础条件：未逻辑删除
        params: list = []

        # 1. 状态筛选（IN）
        if statuses:
            status_list = [int(s) for s in _split_list_param(statuses)]
            where.append(f"status IN ({','.join(['%s']*len(status_list))})")
            params.extend(status_list)


        # 3. AND关键词：必须同时包含所有关键词
        if and_keywords:
            and_list = _split_list_param(and_keywords)
            for kw in and_list:
                where.append("LOWER(prompt) LIKE %s")
                params.append(f"%{kw.lower()}%")

        # 4. OR关键词：至少包含一个关键词
        if or_keywords:
            or_list = _split_list_param(or_keywords)
            or_conditions = [f"LOWER(prompt) LIKE %s" for _ in or_list]
            where.append(' OR '.join(or_conditions))
            params.extend([f"%{kw.lower()}%" for kw in or_list])

        # 拼接WHERE子句
        where_sql = " AND ".join(where) if where else "1=1"

        # 5. 统计总数
        cursor.execute(f"SELECT COUNT(*) AS cnt FROM filter_condition WHERE {where_sql}", params)
        total = cursor.fetchone()["cnt"] if cursor.fetchone() else 0

        # 6. 分页查询数据
        offset = (page - 1) * page_size
        cursor.execute(f"""
        SELECT id, prompt, status, is_deleted, created_at, updated_at
        FROM filter_condition
        WHERE {where_sql}
        ORDER BY id DESC
        LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        rows = cursor.fetchall()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "list": rows
        }
    except pymysql.MySQLError as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
