import sys
import json
import subprocess
import tempfile
import re
import os

def sign_data(data, cert_subject="Благодаренко Юрий Юрьевич"):
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f_in:
        f_in.write(data)
        input_path = f_in.name
    print(f"input {input_path}")
    
    output_path = input_path + '.sig'
    print(f'output {output_path}')
    
    try:
        subprocess.run([
            '/opt/cprocsp/bin/amd64/csptest',
            '-sfsign', '-sign',
            '-in', input_path,
            '-out', output_path,
            '-my', cert_subject,
            '-detached', '-base64', '-add'
        ], check=True)
        
        with open(output_path, 'r') as f_out:
            signature = f_out.read()
        
        return re.sub(r'-----(BEGIN|END) SIGNATURE-----|\s+', '', signature)
    
    finally:
        for path in [input_path, output_path]:
            if os.path.exists(path):
                os.remove(path)

if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            data = sys.argv[1]
            # Поддержка как строки, так и JSON
            if data.startswith('"') or data.startswith('{'):
                try:
                    data = json.loads(data)
                except:
                    pass
            print(sign_data(str(data)))
    except Exception as e:
        print(json.dumps({"error": str(e) }))
        sys.exit(1)
