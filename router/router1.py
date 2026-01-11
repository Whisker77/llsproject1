import json
import re
from typing import Optional, List, Any

import pymysql
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from config import db_config
router1 = APIRouter()



class ConditionBody(BaseModel):
    age: Optional[str] = Field(None)
    major: Optional[str] = Field(None)
    skills: Optional[str] = Field(None)
    degree: Optional[str] = Field(None)
    bachelor_school_level: Optional[str] = Field(None)
    graduate_school_level: Optional[str] = Field(None)
    is_engineering_degree: Optional[str] = Field(None)
    status: Optional[int] = 1



def _get_connection():
    return pymysql.connect(**db_config, cursorclass=pymysql.cursors.DictCursor)


def _dump_condition_json(condition_dict: dict) -> str:
    return json.dumps(condition_dict, ensure_ascii=False) #生成json格式


def _parse_condition_json(raw_value: Any) -> dict:
    if not raw_value:
        return {}
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str):
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError:
            return {}
    return {}

def _format_condition_summary(condition: dict) -> str:
    parts = []

    age = condition.get("age")
    if age:
        parts.append(f"年龄:{age}")   #'年龄:<30'

    majors = condition.get("major")
    if majors:
        if isinstance(majors, list):
            parts.append(f"专业:{'/'.join(majors)}")
        else:
            parts.append(f"专业:{majors}")

    skills = condition.get("skills")
    if skills:
        if isinstance(skills, list):
            parts.append(f"技能:{'/'.join(skills)}")
        else:
            parts.append(f"技能:{skills}")

    degree = condition.get("degree")
    if degree:
        parts.append(f"学历:{degree}")

    bachelor_school_level = condition.get("bachelor_school_level")
    if bachelor_school_level is not None:
        parts.append(f"本科学校水平:{bachelor_school_level}")

    graduate_school_level = condition.get("graduate_school_level")
    if graduate_school_level is not None:

        parts.append(f"研究生学校水平:{graduate_school_level}")

    is_engineering_degree = condition.get("is_engineering_degree")
    if is_engineering_degree is not None:
        parts.append(f"是否工科:{is_engineering_degree}")

    return "；".join(parts) if parts else "无筛选条件" #"学历:硕士;是否工科:否"

def _clean_condition_dict(condition_dict: dict) -> dict:
    """
    清理条件字典：移除值为无效值的键
    无效值包括：None、空字符串、"string"、"null"、纯空格字符串
    """
    invalid_values = [None, "", "string", "null"]
    cleaned_dict = {}
    for key, value in condition_dict.items():
        # 跳过无效值
        if value in invalid_values:
            continue
        # 处理字符串：去掉首尾空格后如果为空，也跳过
        if isinstance(value, str) and value.strip() == "":
            continue
        # 保留有效值
        cleaned_dict[key] = value
    return cleaned_dict

@router1.post('/add_filter_condition',summary='新增筛选条件')
async def add_filter_condition(req: ConditionBody):
    conn = _get_connection()
    cursor = conn.cursor()

    try:
        # 1) 取出要存的 JSON（去掉 None 字段）
        condition_dict = req.model_dump(exclude_none=True)        #model_dump转为字典
        condition_dict = _clean_condition_dict(condition_dict)  # 再过滤"string"/空字符串等
        condition_json_str = _dump_condition_json(condition_dict) #转为json格式，去掉none的条件

        # 2) 插入
        sql = """
        INSERT INTO filter_condition (condition_json, is_deleted)
        VALUES (%s, 0)
        """
        cursor.execute(sql, condition_json_str) #("""INSERT INTO filter_condition (condition_json, is_deleted)VALUES (%s, 0)""",condition_json_str)
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
        SELECT id, condition_json, status,is_deleted
        FROM filter_condition
        ORDER BY id DESC
        """
        cursor.execute(sql)
        rows = cursor.fetchall()

        summaries = []
        for row in rows:
            condition_json = _parse_condition_json(row.get("condition_json")) #condition_json是字典
            summaries.append(
                {
                    "id": row["id"],
                    "status": row["status"],
                    'is_deleted': row["is_deleted"],
                    "summary": _format_condition_summary(condition_json), #这个是返回字符串
                    "condition": condition_json,
                }
            )

        return {"total": len(summaries), "list": summaries}

    except pymysql.MySQLError as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()





class UpdateFilterConditionReq(BaseModel):
    id: int = Field(..., gt=0)
    condition: Optional[ConditionBody] = None


@router1.put("/update_filter_condition", summary="更新筛选条件")
async def update_filter_condition(req: UpdateFilterConditionReq):
    conn = _get_connection()

    cursor = conn.cursor()
    try:
        update_fields = []  #['name=%s','condition_json={'major':..,'skill':..}','status:%s']
        params = []

        if req.condition is not None:
            condition_dict = req.condition.model_dump(exclude_none=True)
            condition_dict = _clean_condition_dict(condition_dict)  # 新增这行
            condition_json_str = _dump_condition_json(condition_dict)
            update_fields.append("condition_json=%s")

            params.append(condition_json_str)


        if not update_fields:
            raise HTTPException(status_code=400, detail="没有需要更新的字段")

        sql = f"""
        UPDATE filter_condition
        SET {",".join(update_fields)}
        WHERE id=%s AND is_deleted=0
        """
        params.append(req.id)

        cursor.execute(sql, params)     #占位符+绑定参数
        conn.commit()

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="记录不存在或已删除")

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



@router1.get("/list_filter_condition", summary="分页查询筛选条件（支持多状态+多条件）")
async def list_filter_condition(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),

    # 表字段 status：支持多状态
    statuses: str | None = Query(None, description="表字段status多状态：如 0,1 或 0 1"),

    # ======= condition_json 内的筛选条件（多条件 AND） =======
    age: str | None = Query(None, description="(如 >40)"),
    majors: str | None = Query(None, description="包含：如 计算机,软件工程"),
    skills: str | None = Query(None, description="包含：如 Python,FastAPI"),
    degree: str | None = Query(None, description="如：本科/硕士"),
    bachelor_school_level: int | None = Query(None, description="985,211?"),
    graduate_school_level: int | None = Query(None, description="985,211?"),
    is_engineering_degree: str | None = Query(None, description="是/否"),
):
    conn = _get_connection()
    cursor = conn.cursor()
    try:
        where = ["is_deleted=0"]
        params: list = []

        # 1) 多状态（表字段 status）
        if statuses:
            status_list = [int(s) for s in _split_list_param(statuses)]
            if status_list:
                where.append("status IN (" + ",".join(["%s"] * len(status_list)) + ")")
                params.extend(status_list)

        # 2) ======= condition_json 多条件（全部 AND） =======

        # age：你存的是字符串（Optional[str]），这里做“精确匹配”
        if age:
            where.append("JSON_UNQUOTE(JSON_EXTRACT(condition_json, '$.age')) = %s")
            params.append(age)

        # major：包含其一即可
        if majors: #'计算机,信息工程'
            major_list = _split_list_param(majors) #['计算机','信息工程']
            if major_list:
                or_parts = []
                for m in major_list:
                    or_parts.append(
                        "JSON_UNQUOTE(JSON_EXTRACT(condition_json, '$.major')) like %s"
                    ) #JSON_CONTAINS(condition_json, JSON_QUOTE('计算机'), '$.major')  condition_json里的major数据，是不是 “计算机”。
                    params.append(f'%{m}%')    #or_parts = ["JSON_CONTAINS(condition_json, JSON_QUOTE(%s), '$.major')",
                                                      # "JSON_CONTAINS(condition_json, JSON_QUOTE(%s), '$.major')"]
                where.append(f"{" OR ".join(or_parts)}")

        # skills：包含其一即可
        if skills:
            skill_list = _split_list_param(skills)
            if skill_list:
                or_parts = []
                for sk in skill_list:
                    or_parts.append(
                        "JSON_CONTAINS(condition_json, JSON_QUOTE(%s), '$.skills')"
                    )
                    params.append(sk)
                where.append(f"{" OR ".join(or_parts)}")

        # degree：字符串精确匹配
        if degree:
            where.append("JSON_UNQUOTE(JSON_EXTRACT(condition_json, '$.degree')) = %s") #从condition_json中提取degree键
                                                                        # 的值，判断是否等于%s对应的参数（比如‘本科’）”。unquote是去掉双引号
            params.append(degree)

        # bachelor_school_level：
        if bachelor_school_level:
            where.append("""
                JSON_UNQUOTE(
                    JSON_EXTRACT(condition_json, '$.bachelor_school_level')
                ) LIKE %s
            """)
            params.append(f"%{bachelor_school_level}%")

        # post_graduate_school_level：数字精确匹配
        if graduate_school_level:
            where.append("""
                JSON_UNQUOTE(
                    JSON_EXTRACT(condition_json, '$.graduate_school_level')
                ) LIKE %s
            """)
            params.append(f"%{graduate_school_level}%")

        # is_engineering_degree：
        if is_engineering_degree is not None:
            where.append("JSON_UNQUOTE(JSON_EXTRACT(condition_json, '$.is_engineering_degree')) like %s")
            params.append(f'%{is_engineering_degree}%')

        where_sql = " AND ".join(where)

        # 3) total
        cursor.execute(f"SELECT COUNT(*) AS cnt FROM filter_condition WHERE {where_sql}", params)
        total_row = cursor.fetchone()
        total = total_row["cnt"] if total_row else 0

        # 4) list
        offset = (page - 1) * page_size
        cursor.execute(
            f"""
            SELECT id, condition_json, status, is_deleted, created_at, updated_at
            FROM filter_condition
            WHERE {where_sql}
            ORDER BY id DESC
            LIMIT %s OFFSET %s
            """,
            params + [page_size, offset],
        )
        rows = cursor.fetchall()

        # 5) 输出统一：condition_json -> dict
        for row in rows:
            row["condition_json"] = _parse_condition_json(row.get("condition_json"))

        return {"total": total, "page": page, "page_size": page_size, "list": rows}

    except pymysql.MySQLError as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()
