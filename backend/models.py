from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    google_id = Column(String(255), unique=True, nullable=False)
    email = Column(String(255), nullable=False)
    name = Column(String(255))
    picture = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    generations = relationship("Generation", back_populates="user")


class Template(Base):
    """Stores example MOS+RA+SWP pairs uploaded by the team for AI to learn from."""
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)   # NULL = system/Drive template
    project_type = Column(String(100), nullable=False)
    label = Column(String(500))
    mos_text = Column(Text)
    ra_text = Column(Text)               # raw text extracted from uploaded RA
    swp_text = Column(Text)              # raw text extracted from uploaded SWP
    created_at = Column(DateTime, default=datetime.utcnow)


class Generation(Base):
    __tablename__ = "generations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Project details
    project_name = Column(String(500))
    project_type = Column(String(100))  # Green Wall / Green Roof / Construction / Landscape
    location = Column(String(500))
    ra_leader = Column(String(255))
    approved_by = Column(String(255))
    ra_members = Column(JSON)           # list of names
    reference_no = Column(String(255))
    company = Column(String(255))
    client = Column(String(255))
    assessment_date = Column(String(50))

    # Content
    mos_text = Column(Text)
    ra_swp_json = Column(JSON)          # full generated content
    feedback_history = Column(JSON, default=list)  # [{feedback, timestamp}]

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="generations")
    versions = relationship("GenerationVersion", back_populates="generation", order_by="GenerationVersion.version_num")


class GenerationVersion(Base):
    """Snapshot of ra_swp_json content at a point in time, so past versions stay downloadable."""
    __tablename__ = "generation_versions"

    id = Column(Integer, primary_key=True, index=True)
    generation_id = Column(Integer, ForeignKey("generations.id"), nullable=False)
    version_num = Column(Integer, nullable=False)
    ra_swp_json = Column(JSON)
    feedback = Column(Text, nullable=True)  # None for the original (version 1)
    created_at = Column(DateTime, default=datetime.utcnow)

    generation = relationship("Generation", back_populates="versions")


class Project(Base):
    """
    Maintenance-report project directory. Mirrors (but is independent from) the
    Photo-to-Drive bot's config/projects.txt -- 'code' + 'name' together must match
    that bot's project folder naming ("<code> - <name>") for Drive photo search to
    find the right folders. Adding a project here does NOT update the bot's list.
    """
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    address = Column(String(500))
    client = Column(String(255))  # client / main contractor, from the project masterlist
    project_type = Column(String(100))  # e.g. "Green Roof" -- determines checklist item set
    created_at = Column(DateTime, default=datetime.utcnow)


class MaintenanceReport(Base):
    """A generated checklist + photo report for one maintenance visit/period."""
    __tablename__ = "maintenance_reports"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    date_from = Column(String(20))
    date_to = Column(String(20))
    photos = Column(JSON, default=list)  # ordered [{file_id, name, date}], date="YYYY-MM-DD"
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project")
