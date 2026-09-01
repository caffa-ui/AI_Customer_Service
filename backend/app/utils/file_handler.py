import os
import hashlib
from app.utils.logger_handler import get_logger
from langchain_core.documents import Document
from langchain_community.document_loaders import TextLoader,PyPDFLoader

logger=get_logger("file_handler")

def get_file_md5_hex(filepath: str):

    if not os.path.exists(filepath):
        logger.error(f"[md5计算]文件{filepath}不存在")
        return None

    if not os.path.isfile(filepath):
        logger.error(f"[md5计算]路径{filepath}不是文件")
        return None

    md5_obj= hashlib.md5()

    chunk_size=4096
    try:
        with open(filepath,"rb") as f:
            while chunk:=f.read(chunk_size):
                md5_obj.update(chunk)
            md5_hex=md5_obj.hexdigest()
            return md5_hex
    except Exception as e:
        logger.error(f"计算文件{filepath}md5失败,{str(e)}")
        return None

def pdf_loader(file_path:str,password:str=None)->list[Document]:
    return PyPDFLoader(file_path,password).load()

def txt_loader(file_path:str)->list[Document]:
    return TextLoader(file_path,encoding="utf-8").load()
