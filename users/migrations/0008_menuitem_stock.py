from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0007_contactotp'),
    ]

    operations = [
        migrations.AddField(
            model_name='menuitem',
            name='stock',
            field=models.PositiveIntegerField(default=20),
        ),
    ]
