from django.core.files.storage import FileSystemStorage

class PassthroughURLStorage(FileSystemStorage):
    def url(self, name):
        if isinstance(name, str) and (name.startswith('http://') or name.startswith('https://')):
            # Return the stored value without MEDIA_URL
            return name
        return super().url(name)
