from django.db import models
from django.utils import timezone
from agencyusers.models import Users  # varsa dışa aktarman gerekebilir


class OTP(models.Model):
    user = models.OneToOneField("agencyusers.Users", on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    last_sent_at = models.DateTimeField(default=timezone.now)

    is_verified = models.BooleanField(default=False)

    # 👉 Kullanıcının acente ve şube bilgilerini saklamak için
    agency = models.ForeignKey("agency.Agency", on_delete=models.SET_NULL, null=True, blank=True)
    branch = models.ForeignKey("agency.Branch", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = "otp_codes"


class LoginActivity(models.Model):
    user = models.ForeignKey(Users, on_delete=models.CASCADE)
    agency = models.ForeignKey("agency.Agency", on_delete=models.SET_NULL, null=True, blank=True)
    branch = models.ForeignKey("agency.Branch", on_delete=models.SET_NULL, null=True, blank=True)

    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    login_time = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.user.username} - {self.ip_address} - {self.login_time}"

    class Meta:
        db_table = "LoginActivity"  # <- bu çok önemli
