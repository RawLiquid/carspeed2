"""
database files
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base

engine = create_engine('postgresql://speedcam:Rward0232@localhost/speedcamdb')
Base = declarative_base()

__all__ = ['speeders', 'vehicles', 'log']


class Log(Base):
    """
    Table for Log
    """

    __tablename__ = "log"
    id = Column(Integer, primary_key=True, index=True)
    sessionID = Column(String, unique=True)
    timeOn = Column(DateTime, index=True)
    timeOff = Column(DateTime, index=True)


class Speeders(Base):
    """
    Table for Speeders
    """

    __tablename__ = "speeders"
    id = Column(Integer, primary_key=True, index=True)
    sessionID = Column(String, ForeignKey(Log.sessionID))
    datetime = Column(DateTime, index=True)
    speed = Column(Float, index=True)
    rating = Column(Float)


class Vehicles(Base):
    """
    Table for all vehicles
    """

    __tablename__ = "vehicles"
    id = Column(Integer, primary_key=True, index=True)
    sessionID = Column(String, ForeignKey(Log.sessionID))
    datetime = Column(DateTime, index=True)
    speed = Column(Float, index=True)
    rating = Column(Float)


Base.metadata.create_all(engine, checkfirst=True)
