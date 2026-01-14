import pymysql

# ---------------------- 1. 数据库连接配置 ----------------------
db_config = {
    "host": "127.0.0.1",    # 数据库主机
    "port": 3306,           # 数据库端口
    "user": "root",         # 数据库用户名
    "password": "123456",  # 数据库密码
    "database": "resume" # 要操作的数据库
}

# ---------------------- 2. 连接数据库并创建表 ----------------------
try:
    # 建立数据库连接
    conn = pymysql.connect(**db_config)
    cursor = conn.cursor()  # 创建游标对象（执行SQL用）

    create_table_sql1 = '''
CREATE TABLE filter_condition (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  prompt text not null comment '大模型提示词,筛选条件',
  format_prompt text not null comment '输出格式的提示词',
  is_deleted TINYINT(1) NOT NULL DEFAULT 0 COMMENT '逻辑删除 0-正常 1-删除',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  status int not null default 1 comment '条件状态 0-不可被选用 1-可被选用'
)
ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 comment = '筛选条件表';
'''



    create_table_sql2 = """
    CREATE TABLE IF NOT EXISTS resume_info_table (
        id int auto_increment primary key comment '主键id',
        candidate_name varchar(50) not null comment '候选人姓名',
        age int not null comment '候选人年龄',
        contact varchar(50) comment '联系方式',
        major varchar(50) not null comment '专业',
        skill json not null comment '技能',
        degree varchar(50) not null comment '学历水平', -- 可以是大专、本科、硕士、博士，不写研究生这种模糊表达
        bachelor_school varchar(50) default null comment '本科毕业院校',
        bachelor_school_level varchar(50) default null comment '本科学校水平，国内指985211，国外指qs排名', -- 国内学校写成985,211,海外就写12
        graduate_school varchar(50) default null comment '研究生毕业学校', 
        graduate_school_level varchar(50) default null comment '研究生毕业学校水平，国内指985211，国外指qs排名',
        is_engineering_degree varchar(50) not null comment '是否为工科专业',
        resume_minio_path text default null comment '简历保存路径',
        avatar_minio_path text default null comment '头像图片保存路径',
        resume_file_name varchar(100) comment '简历原文件名',
        create_time datetime default current_timestamp comment '记录创建时间'
    ) engine=innodb default charset=utf8mb4 comment='基础简历信息表';
    """

    create_table_sql3 = """
        CREATE TABLE IF NOT EXISTS talent_info_table (
            id int auto_increment primary key comment '主键id',
            filter_condition_id int not null comment '筛选条件的id',
            candidate_name varchar(50) not null comment '候选人姓名',
            age int not null comment '候选人年龄',
            contact varchar(50) comment '联系方式',
            major varchar(50) not null comment '专业',
            skill json not null comment '技能',
            degree varchar(50) not null comment '学历水平', -- 可以是大专、本科、硕士、博士，不写研究生这种模糊表达
            bachelor_school varchar(50) default null comment '本科毕业院校',
            bachelor_school_level varchar(50) default null comment '本科学校水平，国内指985211，国外指qs排名', -- 国内学校写成mainland,985,211,海外就写oversea,12
            graduate_school varchar(50) default null comment '研究生毕业学校', 
            graduate_school_level varchar(50) default null comment '研究生毕业学校水平，国内指985211，国外指qs排名',
            is_engineering_degree varchar(50) not null comment '是否为工科专业',
            resume_minio_path text default null comment '简历保存路径',
            portrait_minio_path text default null comment '头像图片保存路径',
            resume_file_name varchar(100) comment '简历原文件名',
            select_day date default (current_date) comment '选拔日'
        ) engine=innodb default charset=utf8mb4 comment='满足筛选的人才信息表';
        """
    # 执行SQL语句（创建表）
    cursor.execute(create_table_sql1)
    cursor.execute(create_table_sql2)
    cursor.execute(create_table_sql3)
    conn.commit()  # 提交事务
    print("人才项目数据库表创建成功！")

except pymysql.MySQLError as e:
    print(f"数据库操作失败：{e}")
    conn.rollback()  # 出错时回滚到上一次commit后的状态

finally:
    # 关闭游标和连接
    cursor.close()
    conn.close()


