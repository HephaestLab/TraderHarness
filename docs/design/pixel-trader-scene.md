# Pixel Trader Scene — V6 Final Design

## 核心约束（不可违反）

1. **所有资产统一 32px 像素密度** — 一个 tile = 32x32，角色 = 32x48，家具按 tile 倍数
2. **统一视角：正面 45° 俯视** — 传统 RPG（星露谷/Undertale 房间）
3. **依赖树生成** — 每个资产生成时，必须把它的"父依赖"作为图片输入

## 依赖树（生成顺序）

```
Level 0: 风格参考图（锁定整体美术方向、调色板、像素密度）
    │
    ├── Level 1: 地砖 tile（参考图作为输入）
    │     ├── tile_floor.png (32x32)
    │     └── tile_wall.png (32x32)
    │
    ├── Level 1: 角色基础形象（参考图作为输入）
    │     └── character_base.png — 单帧正面站立，32x48
    │           │
    │           ├── Level 2: 角色行走 spritesheet（character_base 作为输入）
    │           │     └── character_walk.png — 4方向 x 4帧 = 16帧
    │           │
    │           └── Level 2: 交互动画（character_base + 对应家具 作为输入）
    │                 ├── interact_sit_type.png (base + desk)
    │                 ├── interact_sit_think.png (base + desk)
    │                 ├── interact_coffee.png (base + coffee)
    │                 ├── interact_sofa.png (base + sofa)
    │                 ├── interact_whiteboard.png (base + whiteboard)
    │                 ├── interact_read.png (base + bookshelf)
    │                 ├── interact_server.png (base + server)
    │                 ├── interact_celebrate.png (base only)
    │                 └── interact_frustrated.png (base only)
    │
    └── Level 1: 家具（参考图作为输入，统一视角和像素密度）
          ├── furniture_desk.png (96x64 = 3x2 tiles)
          ├── furniture_chair.png (32x32 = 1x1 tile)
          ├── furniture_coffee.png (32x64 = 1x2 tiles)
          ├── furniture_sofa.png (64x48 = 2x1.5 tiles)
          ├── furniture_server.png (32x64 = 1x2 tiles)
          ├── furniture_bookshelf.png (64x32 = 2x1 tiles)
          ├── furniture_whiteboard.png (64x64 = 2x2 tiles)
          ├── furniture_plant.png (32x32 = 1x1 tile)
          ├── furniture_lamp.png (32x64 = 1x2 tiles)
          ├── furniture_rug.png (128x96 = 4x3 tiles, floor level)
          ├── furniture_filing.png (32x64 = 1x2 tiles)
          ├── furniture_water.png (32x64 = 1x2 tiles)
          ├── furniture_clock.png (32x32 = wall decoration)
          └── furniture_poster.png (32x32 = wall decoration)
```

## 像素规格（严格执行）

| 资产类型 | 逻辑像素 | 生成尺寸 | 说明 |
|---------|---------|---------|------|
| Tile | 32x32 | 32x32 实际 | 不缩放，原始尺寸 |
| 角色基础 | 32x48 | 请求32x48区域内容 | 1 tile 宽 1.5 tile 高 |
| 角色行走 | 128x192 | 4列x4行，每格32x48 | 16帧 |
| 交互帧 | 128x48 | 4列x1行，每格32x48 | 4帧 |
| 小家具 | 32x32~32x64 | 1~2 tile 大小 | 椅子/植物/灯 |
| 中家具 | 64x48~64x64 | 2~2 tile 大小 | 沙发/书架/白板 |
| 大家具 | 96x64 | 3x2 tile | 桌子 |
| 地面装饰 | 128x96 | 4x3 tile | 地毯 |

## 调色板（所有资产共享）

```
地板: #c8956c, #b8855c, #a07550
墙壁: #3d2850, #2d1f3d, #4a3060
木材: #8b5e3c, #6b4530, #a07048
紫色(家具/衣服): #6b3a7d, #4a2860, #8854a0
青绿(地毯/装饰): #3d8b8b, #2d6b6b, #508080
皮肤: #f0c890, #d4a870
头发: #2d1f3d, #1a1020
灯光暖色: #f0c060, #ffdd80
屏幕冷色: #40d0d0, #60ff80, #ff5050
```

## 生成 Prompt 中必须包含的统一约束

每个 prompt 都必须包含以下前缀：

```
"32-pixel-grid pixel art. Exactly 32 pixels = 1 tile. 
正面45度俯视视角 (front-facing 45-degree top-down RPG perspective, like Stardew Valley).
Clean crisp pixels, visible pixel grid, absolutely NO anti-aliasing or sub-pixel smoothing.
Every pixel must be a solid flat color — no gradients, no soft edges, no glow effects."
```

## 场景网格 (20x20 tiles = 640x640 px)

```
Row 0:  [W][W][W][W][W][W][W][W][W][W][W][W][W][W][W][W][W][W][W][W]
Row 1:  [W][.][.][.][.][.][.][.][.][.][.][.][.][.][.][.][.][.][.][W]
Row 2:  [W][.][DESK-------][.][.][.][WB--][.][.][CF][.][.][.][SV][W]
Row 3:  [W][.][DESK-------][.][.][.][WB--][.][.][CF][.][.][.][SV][W]
Row 4:  [W][.][.][CH][.][.][.][.][.][.][.][.][.][.][.][.][.][.][W]
Row 5:  [W][.][.][.][.][.][.][.][.][.][.][.][.][.][.][.][.][.][.][W]
Row 6:  [W][FL][.][.][.][RUG-----------][.][.][.][.][.][.][LP][.][W]
Row 7:  [W][FL][.][.][.][RUG-----------][.][.][.][.][.][.][.][.][W]
Row 8:  [W][.][.][.][.][RUG-----------][.][.][.][.][.][.][.][.][W]
Row 9:  [W][.][.][.][.][.][.][.][.][.][.][.][SOFA----][.][.][.][W]
...
Row 16: [W][PL][.][.][.][.][BS------][.][.][.][.][.][.][.][WC][W]
Row 17: [W][.][.][.][.][.][BS------][.][.][.][.][.][.][.][.][.][W]
...
Row 19: [W][W][W][W][W][W][W][W][W][W][W][W][W][W][W][W][W][W][W][W]

W=墙, .=地板, CH=椅子, CF=咖啡, SV=服务器, WB=白板, 
FL=文件柜, LP=灯, PL=植物, BS=书架, WC=饮水机
```
