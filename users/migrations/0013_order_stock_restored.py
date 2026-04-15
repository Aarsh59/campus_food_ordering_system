# Generated migration to add stock_restored field to Order model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0012_add_payment_upi_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='stock_restored',
            field=models.BooleanField(default=False),
        ),
    ]
