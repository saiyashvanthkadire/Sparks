import os
import unittest
from unittest.mock import patch, MagicMock
import io

# Set dummy API key to avoid OpenAI client initialization error if .env is missing
os.environ['OPENAI_API_KEY'] = 'test-key'

from app import app

class AppTestCase(unittest.TestCase):
    def setUp(self):
        # use in-memory database for tests to avoid file I/O
        app.DATABASE = ':memory:'
        with app.app_context():
            db = app.get_db()
            # create tables
            db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password TEXT NOT NULL,
                    email TEXT NOT NULL
                )
            ''')
            db.execute('''
                CREATE TABLE IF NOT EXISTS food_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    image_data TEXT NOT NULL,
                    analysis_result TEXT NOT NULL,
                    visibility TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            db.commit()

        self.app = app.test_client()
        self.app.testing = True

    @patch('app.render_template')
    def test_index_get(self, mock_render_template):
        """Test that the index page loads correctly via GET."""
        # Mock render_template to return a simple string
        mock_render_template.return_value = "<html><body>Index Page</body></html>"
        
        response = self.app.get('/medical.html')
        
        self.assertEqual(response.status_code, 200)
        # Verify render_template was called with initial empty values
        mock_render_template.assert_called_with("medical.html", result="", image_data=None, mime_type=None)

    @patch('app.render_template')
    @patch('app.client.chat.completions.create')
    def test_index_post_valid_image(self, mock_create, mock_render_template):
        """Test that a valid image POST request is processed correctly."""
        # Mock render_template
        mock_render_template.return_value = "<html><body>Result Page</body></html>"

        # Mock the OpenAI response
        mock_response = MagicMock()
        mock_message = MagicMock()
        # Markdown content that should be converted to HTML
        mock_message.content = "# Assessment\n\n1. Visible: Cut"
        mock_response.choices = [MagicMock(message=mock_message)]
        mock_create.return_value = mock_response

        # Create a dummy image file
        data = {
            'image': (io.BytesIO(b'fakeimagebytes'), 'test.jpg')
        }

        response = self.app.post('/medical.html', data=data, content_type='multipart/form-data')

        self.assertEqual(response.status_code, 200)
        
        # Verify OpenAI API was called
        mock_create.assert_called_once()
        
        # Verify render_template was called with processed data
        args, kwargs = mock_render_template.call_args
        self.assertEqual(args[0], "medical.html")
        self.assertIn("<h1>Assessment</h1>", kwargs['result']) # Check markdown conversion
        self.assertIsNotNone(kwargs['image_data'])
        self.assertEqual(kwargs['mime_type'], 'image/jpeg')

    def test_index_post_missing_file(self):
        """Test that POST request without 'image' field returns 200 (handled gracefully)."""
        response = self.app.post('/medical.html', data={})
        self.assertEqual(response.status_code, 200)

    def test_save_food_redirects_when_not_logged_in(self):
        """Unauthenticated users should be sent to index.html when trying to save."""
        response = self.app.post('/save_food', data={})
        # Flask redirect when session not loggedin
        self.assertEqual(response.status_code, 302)
        self.assertIn('/index.html', response.headers['Location'])

    def test_save_food_logged_in_stores_entry(self):
        """Logged-in user can save a food entry which is inserted into DB."""
        # first create a user
        with app.app_context():
            db = app.get_db()
            db.execute('INSERT INTO users (username, password, email) VALUES (?,?,?)',
                       ('foo', 'bar', 'foo@example.com'))
            db.commit()
            user = db.execute('SELECT * FROM users WHERE username=?', ('foo',)).fetchone()
            self.assertIsNotNone(user)
            user_id = user['id']

        # simulate login
        with self.app.session_transaction() as sess:
            sess['loggedin'] = True
            sess['id'] = user_id
            sess['username'] = 'foo'

        # post save data
        data = {
            'image_data': 'somebase64',
            'result': 'Diet Idea: Test\nDescription',
            'visibility': 'public'
        }
        response = self.app.post('/save_food', data=data)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/index.html', response.headers['Location'])

        # verify row inserted
        with app.app_context():
            db = app.get_db()
            row = db.execute('SELECT * FROM food_entries WHERE user_id=?', (user_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row['visibility'], 'public')
            self.assertIn('Diet Idea', row['analysis_result'])

    @patch('app.render_template')
    def test_food_get(self, mock_render_template):
        """Test that the food page loads correctly via GET."""
        mock_render_template.return_value = "<html><body>Food Page</body></html>"
        
        response = self.app.get('/Food.html')
        
        self.assertEqual(response.status_code, 200)
        mock_render_template.assert_called_with("Food.html", result="", image_data=None, mime_type=None)

    @patch('app.render_template')
    @patch('app.client.chat.completions.create')
    def test_food_post_valid_image(self, mock_create, mock_render_template):
        """Test that a valid image POST request to Food Assist is processed correctly."""
        mock_render_template.return_value = "<html><body>Food Result</body></html>"

        mock_response = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "# Nutrition\n\n1. Calories: 500"
        mock_response.choices = [MagicMock(message=mock_message)]
        mock_create.return_value = mock_response

        data = {
            'image': (io.BytesIO(b'fakefoodbytes'), 'food.jpg')
        }

        response = self.app.post('/Food.html', data=data, content_type='multipart/form-data')

        self.assertEqual(response.status_code, 200)
        mock_create.assert_called_once()
        
        args, kwargs = mock_render_template.call_args
        self.assertEqual(args[0], "Food.html")
        self.assertIn("<h1>Nutrition</h1>", kwargs['result'])
        self.assertIsNotNone(kwargs['image_data'])

if __name__ == '__main__':
    unittest.main()