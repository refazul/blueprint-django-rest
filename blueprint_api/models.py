# models.py

from django.db import models
from django.utils.text import slugify
from django.utils import timezone
import re
import random
from .storages import PassthroughURLStorage