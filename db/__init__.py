"""
database files
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, create_engine
from sqlalchemy.ext.declarative import declarative_base

engine = create_engine('postgresql://speedcam:Rward0232@localhost/speedcamdb')
Base = declarative_base()

__all__ = ['speeders']


class Speeders(Base):
    """
    Table for Humans
    """

    __tablename__ = "speeders"
    id = Column(Integer, primary_key=True, index=True)
    uniqueID = Column(String, index=True)
    datetime = Column(DateTime, index=True)
    speed = Column(Float, index=True)
    rating = Column(Integer)

Base.metadata.create_all(engine, checkfirst=True)
