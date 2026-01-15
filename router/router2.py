from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from typing import List
import io
import fitz  # PyMuPDF
import pymysql
import os
import requests
import re
from openai import OpenAI
from datetime import timedelta
import json

# 初始化路由
router2 = APIRouter()

# ====================== 核心配置（根据你的环境修改） ======================
# MinIO配置（关键：用数据端口9100，不是控制台9101）
MINIO_CONF = {
    "host": "localhost",
    "port": 9100,  # MinIO数据API端口（控制台是9101）
    "access_key": "minioadmin",
    "secret_key": "minioadmin"
}

# 数据库配置（替换为你的实际信息）
DB_CONF = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "123456",  # 改成你的MySQL密码
    "database": "resume",    # 改成你的数据库名
    "charset": "utf8mb4"
}

# 大模型配置（DeepSeek）
LLM_CLIENT = OpenAI(
    api_key="sk-31b46a6c0f604d92b20d636aa8ddaad7",
    base_url="https://api.deepseek.com"
)

# ====================== 1. MinIO上传核心函数（适配9100端口） ======================
from io import BytesIO
from config import minio_client
from minio.error import S3Error
from fastapi import HTTPException

def upload_to_minio(file_bytes: bytes, bucket_name: str, object_name: str, content_type: str):
    try:
        # 1) bucket 不存在就创建
        if not minio_client.bucket_exists(bucket_name):
            minio_client.make_bucket(bucket_name)

        # 2) 上传对象
        data = BytesIO(file_bytes)
        minio_client.put_object(
            bucket_name=bucket_name,
            object_name=object_name,
            data=data,
            length=len(file_bytes),
            content_type=content_type
        )

        return f"{bucket_name}/{object_name}"

    except S3Error as e:
        raise HTTPException(status_code=500, detail=f"MinIO S3Error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MinIO异常: {e}")


# ====================== 2. PDF解析+头像提取 ======================
def extract_pdf_content_and_avatar(pdf_bytes: bytes):
    """解析PDF：提取文本 + 智能识别头像"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    raw_text = ""
    candidate_avatars = []

    try:
        # 提取全文本
        for page in doc:
            raw_text += page.get_text()
        # 提取所有图片，筛选头像特征
        for page in doc:
            page_rect = page.rect
            page_width = page_rect.width
            page_height = page_rect.height

            for img in page.get_images(full=True):
                try:
                    xref = img[0]
                    base_img = doc.extract_image(xref)
                    img_bytes = base_img["image"]
                    img_ext = base_img["ext"] or "png"
                    # 获取图片位置和尺寸
                    matched_imgs = [i for i in page.get_image_info(xrefs=True) if i["xref"] == xref]
                    img_info = matched_imgs[0] if matched_imgs else None
                    if not img_info:
                        continue

                    bbox = img_info["bbox"]
                    x0, y0, x1, y1 = bbox
                    w = x1 - x0
                    h = y1 - y0

                    # 头像筛选规则：正方形+小尺寸+顶部/侧边
                    if 30 <= w <= 600 and 30 <= h <= 600:  # 尺寸合理
                        aspect_ratio = min(w, h) / max(w, h)
                        if aspect_ratio >= 0.6:  # 接近正方形
                            # 优先顶部/侧边
                            if y0 < page_height * 0.3 or x0 < page_width * 0.4 or x0 > page_width * 0.6:
                                candidate_avatars.append({
                                    "bytes": img_bytes,
                                    "ext": img_ext
                                })   #candidate-avatars=[{'bytes':123214,''ext':'png'},
                except Exception as e:
                    print(f"图片提取失败: {e}")
                    continue

        # 选第一个符合条件的头像
        avatar = candidate_avatars[0] if candidate_avatars else None  #{'bytes':123214,''ext':'png'}
        return raw_text.strip(), avatar
    finally:
        doc.close()

# ====================== 3. 大模型筛选+信息提取 ======================
_KNOWN_985_SCHOOLS = {
    "北京大学",
    "清华大学",
    "复旦大学",
    "上海交通大学",
    "南京大学",
    "浙江大学",
    "中国科学技术大学",
    "哈尔滨工业大学",
    "西安交通大学",
    "北京航空航天大学",
    "北京理工大学",
    "同济大学",
    "东南大学",
    "天津大学",
    "南开大学",
    "中山大学",
    "华中科技大学",
    "武汉大学",
    "厦门大学",
    "山东大学",
    "吉林大学",
    "四川大学",
    "重庆大学",
    "华南理工大学",
    "中国人民大学",
    "北京师范大学",
    "中国农业大学",
    "西北工业大学",
    "大连理工大学",
    "中南大学",
    "湖南大学",
    "中国海洋大学",
    "兰州大学",
    "电子科技大学",
    "西北农林科技大学",
    "东北大学",
    "中国地质大学(武汉)",
    "中国地质大学(北京)",
    "中央民族大学",
}


def _normalize_school_level(level: str) -> str:
    if not level:
        return "未知"
    normalized = level.strip()
    if normalized in {"无", "未知", "null", "None"}:
        return "未知"
    return normalized


def _infer_school_level(school_name: str, current_level: str) -> str:
    level = _normalize_school_level(current_level)
    if level != "未知":
        return level
    if not school_name:
        return level
    if school_name.strip() in _KNOWN_985_SCHOOLS:
        return "985"
    return level


def llm_process_resume(resume_text: str,prompt:str) -> dict:
    """大模型筛提取简历信息"""
# 简历文本
    try:
        response = LLM_CLIENT.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt+resume_text[:1000]}],
            temperature=0.1
        )
        content = response.choices[0].message.content.strip().split("\n")
        content = [line.strip() for line in content if line.strip()]

        # 解析结果
        resume_info = {
            '姓名':'未知',
            '年龄':'未知',
            '联系方式':'未知',
            '专业':'未知',
            '技能':'未知',
            '学历':'未知',
            '本科毕业院校':'未知',
            '本科学校水平':'未知',
            '研究生毕业院校':'未知',
            '研究生毕业学校水平':'未知',
            '是否工科':'未知'}

        # 提取字段（兼容格式错误）
        if not content:
            raise HTTPException(status=500,detail='未解析出结构化的简历信息')
        for line in content[:]:
            if ":" in line or "：" in line:
                key, val = re.split(r"[:：]", line, maxsplit=1)
                key = key.strip()
                val = val.strip()
                if key in resume_info:
                    resume_info[key] = val

        if resume_info["技能"] != "未知":
            skill_list = [s.strip() for s in resume_info["技能"].split(",") if s.strip()]
            resume_info["技能"] = skill_list  # 直接存数组，不是JSON字符串
        else:
            resume_info["技能"] = []
        # resume_info["年龄"] = int(resume_info["年龄"]) if resume_info["年龄"] not in ["未知", "无", ""] else 0
        resume_info["本科学校水平"] = _infer_school_level(
            resume_info.get("本科毕业院校"),
            resume_info.get("本科学校水平"),
        )
        resume_info["研究生毕业学校水平"] = _infer_school_level(
            resume_info.get("研究生毕业院校"),
            resume_info.get("研究生毕业学校水平"),
        )
        return resume_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"大模型处理失败: {str(e)}")

def fetch_filter_condition(filter_condition_id: int) -> tuple:
    conn = None
    cursor = None
    try:
        conn = pymysql.connect(**DB_CONF)
        cursor = conn.cursor()
        sql = """
            SELECT prompt,format_prompt,status,is_deleted
            FROM filter_condition
            WHERE id=%s 
        """
        cursor.execute(sql, (filter_condition_id,))
        row = cursor.fetchone()  #row是一个元组，包含每个字段的值
        if not row:
            raise HTTPException(status_code=404, detail="筛选条件不存在或已删除")

        prompt,format_prompt,status,is_deleted = row

        if status != 1:
            raise HTTPException(status_code=400, detail="筛选条件不可用")
        if is_deleted == 1:
            raise HTTPException(status_code =400,detail='筛选条件已被逻辑删除')
        return (prompt,format_prompt)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def llm_judge_resume_match(resume_info: dict, condition:str) -> bool:
    if len(condition)==0:
        raise HTTPException(status_code=400,detail='筛选条件为空,请重新设定可用的筛选条件')

    prompt = f"""
你是人才筛选助手，请根据筛选条件判断候选人是否满足条件，仅返回"是"或"否"。

筛选条件（空或null字段表示不限制）：
{json.dumps(condition,ensure_ascii=False)}


候选人信息（JSON）：
{json.dumps(resume_info, ensure_ascii=False)}

判断规则：
上面给你的condition已经给你了明确的筛选条件具体内容和判断准则，包含设定的筛选条件和补充说明的提示词。
你根据已给的筛选规则比对同时给到你的候选人信息做条件判断，输出候选人是否符合筛选条件的判断。
"""
    try:
        response = LLM_CLIENT.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        content = response.choices[0].message.content.strip() #content = '是' 或者 '否'
        return content.startswith("是")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"大模型筛选失败: {str(e)}")

# ====================== 4. 核心接口：简历处理+上传+入库 ======================
@router2.post("/process_resumes")
async def process_resumes(
    filter_condition_id: int = Form(...),
    files: List[UploadFile] = File(...)
):
    results = []
    matched_results = []
    failed_files = []
    avatar_success_count = 0
    prompt_str,format_prompt = fetch_filter_condition(filter_condition_id)
    for file in files:
        try:
            # 1. 校验文件类型
            if not file.filename.lower().endswith(".pdf"):
                raise ValueError(f"文件[{file.filename}]不是PDF格式")

            # 2. 读取PDF字节（仅读一次）
            pdf_bytes = await file.read()
            if not pdf_bytes:
                raise ValueError(f"文件[{file.filename}]为空")

            # 3. 解析PDF（文本+头像）
            try:
                resume_text, avatar = extract_pdf_content_and_avatar(pdf_bytes)
            except Exception as e:
                raise ValueError(f"PDF解析失败: {e}") from e
            if not resume_text.strip():
                raise ValueError("PDF解析无有效文本")

            # 4. 大模型筛选+信息提取
            try:
                resume_info = llm_process_resume(resume_text,format_prompt)
            except HTTPException as e:
                raise ValueError(f"大模型处理失败: {e.detail}") from e

            is_match = llm_judge_resume_match(resume_info,prompt_str)
            pdf_bucket = "b-bucket" if is_match else "a-bucket"
     
            avatar_bucket = "candidate-avatar" if is_match else "resume-avatar"

            # 5. 上传PDF到MinIO
            pdf_object_name = f"resumes/{file.filename}"
            pdf_minio_path = upload_to_minio(
                file_bytes=pdf_bytes,
                bucket_name=pdf_bucket,
                object_name=pdf_object_name,
                content_type="application/pdf"
            )
            pdf_minio_path = 'https://localhost:9101/browser/'+ pdf_minio_path

            # 6. 上传头像到MinIO
            avatar_minio_path = "无头像"
            if avatar:
                avatar_filename = f"{file.filename.rsplit('.', 1)[0]}_avatar.{avatar['ext']}"
                avatar_object_name = f"portraits/{avatar_filename}"
                avatar_minio_path = upload_to_minio(
                    file_bytes=avatar["bytes"],
                    bucket_name=avatar_bucket,
                    object_name=avatar_object_name,
                    content_type=f"image/{avatar['ext']}"
                )
                avatar_minio_path = 'https://localhost:9101/browser/'+avatar_minio_path
                avatar_success_count += 1

            # 7. 数据库入库（适配你的表结构）
            db_status = "未存入"
            conn = None
            cursor = None
            try:
                conn = pymysql.connect(**DB_CONF)
                cursor = conn.cursor()

                # 先查询是否存在重复记录（姓名+学校+专业）
                query_sql = """
                    SELECT id FROM resume_info_table 
                    WHERE TRIM(candidate_name) = TRIM(%s) 
                      AND TRIM(bachelor_school) = TRIM(%s) 
                      AND TRIM(major) = TRIM(%s)
                """
                query_vals = (resume_info["姓名"], resume_info["本科毕业院校"], resume_info["专业"])
                cursor.execute(query_sql, query_vals)
                existing_id = cursor.fetchone()

                if existing_id:
                    # 更新已有记录
                    update_sql = """
                        UPDATE resume_info_table 
                        SET major = %s, skill = %s, degree = %s, bachelor_school = %s,
                            bachelor_school_level = %s, graduate_school = %s, graduate_school_level = %s,
                            is_engineering_degree = %s,resume_minio_path = %s,avatar_minio_path = %s,resume_file_name = %s
                        WHERE id = %s
                    """
                    update_vals = (
                        resume_info['专业'],
                        json.dumps(resume_info["技能"], ensure_ascii=False),
                        resume_info["学历"],
                        resume_info["本科毕业院校"],
                        resume_info['本科学校水平'],
                        resume_info["研究生毕业院校"],
                        resume_info["研究生毕业学校水平"],
                        resume_info['是否工科'],
                        pdf_minio_path,
                        avatar_minio_path,
                        file.filename,
                        existing_id[0]
                    )
                    cursor.execute(update_sql, update_vals)
                    db_status = "已覆盖（ID：{}）".format(existing_id[0])
                else:
                    # 插入新记录（适配所有NOT NULL字段）
                    insert_sql = """
                        INSERT INTO resume_info_table (
                            candidate_name, age, contact,major, skill, degree,
                            bachelor_school,bachelor_school_level,graduate_school,
                            graduate_school_level,is_engineering_degree,resume_minio_path,
                            avatar_minio_path, resume_file_name
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s,%s,%s,%s)
                    """
                    insert_vals = (
                        resume_info["姓名"],
                        resume_info["年龄"],
                        resume_info['联系方式'],
                        resume_info["专业"],
                        json.dumps(resume_info["技能"], ensure_ascii=False),
                        resume_info["学历"],
                        resume_info["本科毕业院校"],
                        resume_info["本科学校水平"],
                        resume_info['研究生毕业院校'],
                        resume_info["研究生毕业学校水平"],
                        resume_info["是否工科"],
                        pdf_minio_path,
                        avatar_minio_path,
                        file.filename
                    )
                    cursor.execute(insert_sql, insert_vals)
                    db_status = "已存入（新ID：{}）".format(cursor.lastrowid)
                conn.commit()
            except Exception as e:
                if conn:
                    conn.rollback()
                db_status = f"存入失败: {str(e)[:30]}" #没有raise Error!
            finally:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()

            # 7.1 满足筛选条件时写入人才信息表
            talent_status = "未存入"
            if is_match:
                conn = None
                cursor = None
                try:
                    conn = pymysql.connect(**DB_CONF)
                    cursor = conn.cursor()

                    # 新增：查询人才表是否存在重复记录
                    talent_query_sql = """
                            SELECT id FROM talent_info_table 
                            WHERE filter_condition_id = %s
                              AND TRIM(candidate_name) = TRIM(%s)
                              AND TRIM(bachelor_school) = TRIM(%s)
                              AND TRIM(major) = TRIM(%s)
                        """
                    talent_query_vals = (
                        filter_condition_id,
                        resume_info["姓名"],
                        resume_info["本科毕业院校"],
                        resume_info["专业"]
                    )
                    cursor.execute(talent_query_sql, talent_query_vals)
                    talent_existing_id = cursor.fetchone()

                    if talent_existing_id:
                        # 重复：执行UPDATE
                        talent_update_sql = """
                                UPDATE talent_info_table 
                                SET age = %s, contact = %s, skill = %s, degree = %s,
                                    bachelor_school_level = %s, graduate_school = %s, graduate_school_level = %s,
                                    is_engineering_degree = %s, resume_minio_path = %s, portrait_minio_path = %s,
                                    resume_file_name = %s, select_day = CURRENT_DATE
                                WHERE id = %s
                            """
                        talent_update_vals = (
                            resume_info["年龄"],
                            resume_info["联系方式"],
                            json.dumps(resume_info["技能"], ensure_ascii=False),
                            resume_info["学历"],
                            resume_info["本科学校水平"],
                            resume_info["研究生毕业院校"],
                            resume_info["研究生毕业学校水平"],
                            resume_info["是否工科"],
                            pdf_minio_path,
                            avatar_minio_path,
                            file.filename,
                            talent_existing_id[0]
                        )
                        cursor.execute(talent_update_sql, talent_update_vals)
                        talent_status = "已覆盖（ID：{}）".format(talent_existing_id[0])
                    else:
                        insert_sql = """
                            INSERT INTO talent_info_table (
                                filter_condition_id, candidate_name, age, contact, major, skill, degree,
                                bachelor_school, bachelor_school_level, graduate_school, graduate_school_level,
                                is_engineering_degree, resume_minio_path, portrait_minio_path, resume_file_name
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s)
                        """
                        insert_vals = (
                            filter_condition_id,
                            resume_info["姓名"],
                            resume_info["年龄"],
                            resume_info["联系方式"],
                            resume_info["专业"],
                            json.dumps(resume_info["技能"], ensure_ascii=False),
                            resume_info["学历"],
                            resume_info["本科毕业院校"],
                            resume_info["本科学校水平"],
                            resume_info["研究生毕业院校"],
                            resume_info["研究生毕业学校水平"],
                            resume_info["是否工科"],
                            pdf_minio_path,
                            avatar_minio_path,
                            file.filename
                        )
                        try:
                            cursor.execute(insert_sql, insert_vals)
                        except pymysql.MySQLError as insert_error:
                            if "Unknown column 'filter_condition_id'" in str(insert_error):
                                insert_sql = insert_sql.replace("filter_condition_id", "filter_condition")
                                cursor.execute(insert_sql, insert_vals)
                            else:
                                raise
                        conn.commit()
                        talent_status = "已存入（新ID：{}）".format(cursor.lastrowid)
                except Exception as e:
                    if conn:
                        conn.rollback()
                    talent_status = f"存入失败: {str(e)[:30]}"
                finally:
                    if cursor:
                        cursor.close()
                    if conn:
                        conn.close()
                matched_results.append({
                    "文件名": file.filename,
                    "筛选条件ID": filter_condition_id,
                    "PDF MinIO路径": pdf_minio_path,
                    "头像MinIO路径": avatar_minio_path,
                    "人才库入库状态": talent_status,
                    "提取的核心信息": {
                        "姓名": resume_info["姓名"],
                        "专业": resume_info["专业"],
                        '年龄': resume_info['年龄'],
                        "学历": resume_info["学历"],
                        "本科毕业院校": resume_info["本科毕业院校"],
                        "本科学校水平": resume_info["本科学校水平"],
                        "研究生毕业院校": resume_info["研究生毕业院校"],
                        "研究生毕业学校水平": resume_info["研究生毕业学校水平"],
                        "是否工科": resume_info["是否工科"],
                        "技能": resume_info["技能"]
                    }
                })

            # 8. 收集结果  如果执行了异常捕获回滚，这里的results.append仍会执行
            results.append({
                "文件名": file.filename,
                "PDF存储Bucket": pdf_bucket,
                "PDF MinIO路径": pdf_minio_path,
                "头像MinIO路径": avatar_minio_path,
                "数据库状态": db_status,
                "筛选条件ID": filter_condition_id,
                "是否满足筛选条件": is_match,
                "人才库入库状态": talent_status,
                "提取的核心信息": {
                    "姓名": resume_info["姓名"],
                    '年龄': resume_info['年龄'],
                    "技能": resume_info["技能"],
                    "联系方式":resume_info['联系方式'],
                    "专业": resume_info["专业"],
                    "学历": resume_info["学历"],
                    "本科毕业院校": resume_info["本科毕业院校"],
                    "本科学校水平": resume_info["本科学校水平"],
                    "研究生毕业院校": resume_info["研究生毕业院校"],
                    "研究生毕业学校水平": resume_info["研究生毕业学校水平"],
                    "是否工科": resume_info["是否工科"],

                }
            })
        except Exception as e:
            failed_files.append({
                "文件名": file.filename,
                "原因": str(e)
            })
            continue

    # 返回汇总结果
    return {
        "本次上传文件总数": len(files),
        "成功上传PDF数": len(results),
        "上传失败数": len(failed_files),
        "上传失败文件": failed_files,
        "成功提取头像数": avatar_success_count,
        "满足筛选条件人数": len(matched_results),
        "满足筛选条件人才详情": matched_results,
        "成功文件详情": results
    }
