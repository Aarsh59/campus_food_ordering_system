from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0009_notification_application_and_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='fulfillment_type',
            field=models.CharField(
                choices=[('DELIVERY', 'Delivery'), ('TAKEOUT', 'Takeout')],
                default='DELIVERY',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='payment_method',
            field=models.CharField(
                choices=[('RAZORPAY', 'Razorpay'), ('COD', 'Cash on delivery')],
                default='RAZORPAY',
                max_length=20,
            ),
        ),
    ]
