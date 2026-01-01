from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)

class LessonRequest(BaseModel):
    subject: str
    topic: str
    level: str = "College of Education"
    duration_min: int = 40

class FeedbackRequest(BaseModel):
    lesson_text: str
    rubric_text: str
