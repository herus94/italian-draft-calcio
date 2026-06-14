const fs = require('fs');
const path = require('path');

const backendUrl = process.env.BACKEND_URL;
if (!backendUrl) {
  console.log('BACKEND_URL not set, skipping API URL injection');
  process.exit(0);
}

const indexPath = path.join(
  __dirname,
  'dist',
  'progetto-calcio-frontend',
  'browser',
  'index.html',
);
let html = fs.readFileSync(indexPath, 'utf8');
html = html.replace(
  '<app-root>',
  `<script>window.__API_URL__='https://${backendUrl}'</script><app-root>`,
);
fs.writeFileSync(indexPath, html);
console.log(`Injected BACKEND_URL: https://${backendUrl}`);
