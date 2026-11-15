from django import forms
from forecast.services.calculation import validate_price

class PriceField(forms.DecimalField):
    def to_python(self, value):
        result = super().to_python(value)
        if result is None:
            return None
        try:
            return validate_price(result)
        except ValueError as error:
            raise forms.ValidationError(str(error), code="unsupported_number") from error

class ForecastInputForm(forms.Form):
    origin = forms.CharField(max_length=80, label="Откуда")
    destination = forms.CharField(max_length=80, label="Куда")
    date = forms.DateField(input_formats=["%Y-%m-%d"], label="Дата")
    price = PriceField(min_value=0, label="Цена")
