import os
import shutil
import uuid
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.database import get_db
from app.models import Project, ProjectFile, User
from app.schemas import ProjectCreate, ProjectFileOut, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}


@router.get("", response_model=List[ProjectOut])
def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(Project)
        .filter(Project.user_id == current_user.id)
        .order_by(Project.created_at.desc())
        .all()
    )


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = Project(name=body.name, user_id=current_user.id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _get_own_project(project_id, current_user.id, db)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _get_own_project(project_id, current_user.id, db)
    db.delete(project)
    db.commit()


@router.post("/{project_id}/files", response_model=ProjectFileOut, status_code=status.HTTP_201_CREATED)
def upload_file(
    project_id: int,
    file_type: str = "tz",
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _get_own_project(project_id, current_user.id, db)
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail=f"Допустимые форматы: PDF, DOCX. Получен: {ext}")

    dest_dir = os.path.join(settings.uploads_dir, str(project.id))
    os.makedirs(dest_dir, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    dest_path = os.path.join(dest_dir, filename)

    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    pf = ProjectFile(
        project_id=project.id,
        filename=file.filename,
        file_path=dest_path,
        file_type=file_type,
    )
    db.add(pf)
    db.commit()
    db.refresh(pf)
    return pf


@router.delete("/{project_id}/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    project_id: int,
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _get_own_project(project_id, current_user.id, db)
    pf = db.query(ProjectFile).filter(ProjectFile.id == file_id, ProjectFile.project_id == project.id).first()
    if not pf:
        raise HTTPException(status_code=404, detail="Файл не найден")
    if os.path.exists(pf.file_path):
        os.remove(pf.file_path)
    db.delete(pf)
    db.commit()


def _get_own_project(project_id: int, user_id: int, db: Session) -> Project:
    project = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Проект не найден")
    return project
