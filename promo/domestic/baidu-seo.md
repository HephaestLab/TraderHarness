# 国内 SEO + Gitee 镜像操作手册

## 一、百度站长平台（ziyuan.baidu.com）

> 目标：让百度收录文档站 hephaestlab.github.io/TraderHarness/ 和 Gitee 镜像。

1. 注册百度账号 → 登录百度站长平台 →「用户中心 → 站点管理 → 添加网站」
2. 填写 `https://hephaestlab.github.io`（GitHub Pages 是子路径站点，验证主域即可）
3. 验证方式选 **HTML 文件验证**：下载百度给的 `baidu_verify_xxxx.html`，
   发给我——我把它放进 `docs/` 并推送（mkdocs 会原样发布到站点根），然后你点「完成验证」
4. 验证通过后：
   - **sitemap 提交**：`https://hephaestlab.github.io/TraderHarness/sitemap.xml`
     （mkdocs-material 构建时自动生成，已确认 site_url 配置正确）
   - **主动推送**（新页面加速收录，每次 docs 更新跑一次）：
     ```bash
     curl -H 'Content-Type:text/plain' --data-binary @urls.txt \
       "http://data.zz.baidu.com/urls?site=https://hephaestlab.github.io&token=你的token"
     ```
     token 在站长平台「链接提交」页可见；urls.txt 我可以从 sitemap 生成。
5. 「抓取诊断」里手动点一次首页抓取，触发首次收录。

## 二、Gitee 镜像

> 价值：国内访问速度、Gitee 自身流量入口、百度收录（Gitee 页面权重高）、
> README 中文展示完整。

1. 注册 Gitee 账号 → 新建仓库 `TraderHarness`（**不要**初始化 README，保持空仓库）
2. Gitee「设置 → 私人令牌」生成 token（勾选 projects 权限）
3. GitHub 仓库 → Settings → Secrets → 新建 `GITEE_TOKEN`，填入 token
4. 我已提交 `.github/workflows/gitee-mirror.yml`：每次 main 有推送就强制同步到 Gitee。
   之后去 Actions 页手动跑一次确认成功。
5. Gitee 仓库设置里开启「仓库简介 + 推荐」：简介用中文 About 同款文案，
   话题标签加 `量化交易`、`LLM`、`回测`。

## 三、辅助项（可选）

- **360 站长平台 / 搜狗站长**：流程同百度，优先级低，有余力再配。
- **Bing 站长**：之前已做过 IndexNow，无需重复。
- **收录检查**：每周用 `site:hephaestlab.github.io` 和 `site:gitee.com` 在百度搜一次，
  看收录页数增长。
