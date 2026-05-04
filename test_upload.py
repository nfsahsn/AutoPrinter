import io
from app import create_app
from config import Config
from app.extensions import db
from app.models import User

app = create_app(Config)
app.config['TESTING'] = True

with app.test_client() as client:
    with app.app_context():
        if not User.query.get("01700000000"):
            u = User(phone="01700000000", name="Test", password="pwd")
            db.session.add(u)
            db.session.commit()
            
    # Simulate logged in user
    with client.session_transaction() as sess:
        sess['user_phone'] = "01700000000"
        
    data = {
        'file': (io.BytesIO(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"), 'test.pdf'),
        'copies': '1',
        'ptype': 'bw'
    }
    response = client.post('/upload', data=data, content_type='multipart/form-data')
    print("Response status:", response.status_code)
    if response.status_code >= 400:
        print(response.get_data(as_text=True))
