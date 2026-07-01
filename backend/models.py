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
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    project_type = Column(String(100), nullable=False)
    label = Column(String(500))          # e.g. "Green Wall - IWMF example"
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
