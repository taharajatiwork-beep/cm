from app.core.vehicle_labels import fa_vehicle_name


def test_fa_vehicle_name_maps_brand_and_model():
    assert fa_vehicle_name("Toyota", "Camry") == "تویوتا کمری"
    assert fa_vehicle_name("Hyundai", "Elantra") == "هیوندای النترا"
