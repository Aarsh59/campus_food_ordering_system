from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0008_menuitem_stock'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='application',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='notifications',
                to='users.staffapplication',
            ),
        ),
        migrations.AlterField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(
                choices=[
                    ('ORDER_UPDATE', 'Order update'),
                    ('STAFF_APPLICATION', 'Staff application'),
                ],
                default='ORDER_UPDATE',
                max_length=30,
            ),
        ),
    ]
