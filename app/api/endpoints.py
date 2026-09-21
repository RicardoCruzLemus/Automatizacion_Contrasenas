# Endpoints API
from flask import Blueprint

api_bp = Blueprint('api_bp', __name__)

@api_bp.route('/status')
def status():
    return {"status": "ok"}
