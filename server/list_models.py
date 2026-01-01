import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))

print('\nAvailable Gemini models that support generateContent:\n')
for model in genai.list_models():
    if 'generateContent' in model.supported_generation_methods:
        print(f'  ✓ {model.name}')
        print(f'    Display: {model.display_name}')
        print(f'    Description: {model.description}')
        print()
