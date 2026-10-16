import { defineConfig } from 'vite';

export default defineConfig({
  // 音檔放在專案根目錄的 audio/，dev server 要允許讀上一層
  server: { fs: { allow: ['..'] } },
});
