from django.db import models
from django.contrib.auth.models import User

# Create your models here.
class BlogPost(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    y_title = models.CharField(max_length=200)
    y_link = models.URLField()
    gen_content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.y_title


class DailyGenerationCount(models.Model):
    """
    Tracks per-user daily blog generation count for quota enforcement.
    One row per (user, date) — auto-resets at midnight UTC.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [['user', 'date']]

    def __str__(self):
        return f"{self.user.username} — {self.date}: {self.count}"
