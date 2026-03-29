import { useState, useEffect, useCallback, useRef } from 'react'
import { createPortal } from 'react-dom'

// 默认常量（数据库未加载时使用）
const DEFAULT_CHARS = ['李箱', '浮士德', '堂吉诃德', '良秀', '默尔索', '鸿璐', '希斯克里夫', '以实玛丽', '罗佳', '辛克莱', '奥提斯', '格里高尔']
const DEFAULT_TYPES = ['人格', 'E.G.O']
const DEFAULT_SEASONS = ['常驻', '第1赛季', '第2赛季', '第3赛季', '第4赛季', '第5赛季', '第6赛季', '第7赛季']

// Token管理
const getToken = () => localStorage.getItem('token')
const setToken = (token) => localStorage.setItem('token', token || '')
const removeToken = () => localStorage.removeItem('token')

// API调用（带认证）
const api = (url, opts = {}) => {
  const token = getToken()
  console.log(`API [${url}] token: ${token ? token.substring(0, 20) + '...' : 'none'}`)
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...opts.headers,
  }
  return fetch('/api' + url, { ...opts, headers })
    .then(r => {
      if (!r.ok) {
        return r.json().then(err => {
          console.error('API error:', r.status, err)
          throw new Error(err.error || err.message || 'API error')
        })
      }
      return r.json()
    })
    .catch(err => {
      console.error('API call failed:', url, err)
      throw err
    })
}

const Stars = ({ n }) => {
  const sizeMap = { 1: '24px', 2: '26px', 3: '28px' }
  const size = sizeMap[n] || '26px'
  const fileMap = { 1: '12px', 2: '25px', 3: '35px' }
  const fileSize = fileMap[n] || '25px'
  return <img src={`/webp/${fileSize}-稀有度${n}.webp`} alt={`稀有度${n}`} style={{ height: size, verticalAlign: 'middle' }} />
}

// --- MultiSelect: 使用 createPortal 渲染下拉框，彻底避免 overflow 裁剪 ---
function MultiSelect({ options, value, onChange, placeholder }) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef(null)
  const [pos, setPos] = useState({ top: 0, left: 0, width: 160 })

  const allSelected = value.length === 0 || value.length === options.length
  const displayText = allSelected ? placeholder || '全部' : value.length === 1 ? value[0] : `已选 ${value.length} 项`

  const toggle = (e, opt) => {
    e.stopPropagation()
    onChange(value.includes(opt) ? value.filter(v => v !== opt) : [...value, opt])
  }

  const toggleAll = (e) => {
    e.stopPropagation()
    onChange(allSelected ? [] : [...options])
  }

  const calcPos = useCallback(() => {
    if (!triggerRef.current) return
    const r = triggerRef.current.getBoundingClientRect()
    const vw = window.innerWidth
    const vh = window.innerHeight
    const w = Math.max(r.width, 160)
    let left = r.left
    if (left + w > vw - 8) left = vw - w - 8
    if (left < 8) left = 8
    let top = r.bottom + 4
    if (top + 300 > vh) top = r.top - 304
    if (top < 4) top = 4
    setPos({ top, left, width: w })
  }, [])

  // 打开时计算位置 + 监听滚动/resize
  useEffect(() => {
    if (!open) return
    const frame = requestAnimationFrame(calcPos)
    const onScroll = () => calcPos()
    window.addEventListener('scroll', onScroll, true)
    window.addEventListener('resize', calcPos)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('scroll', onScroll, true)
      window.removeEventListener('resize', calcPos)
    }
  }, [open, calcPos])

  // 点击外部关闭
  useEffect(() => {
    if (!open) return
    const handler = (e) => {
      if (triggerRef.current?.contains(e.target)) return
      setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const dropdownEl = open ? (
    <div
      className="ms-dropdown"
      style={{ position: 'fixed', top: pos.top, left: pos.left, width: pos.width }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <div className={`ms-option ${allSelected ? 'ms-checked' : ''}`} onClick={toggleAll}>
        <input type="checkbox" checked={allSelected} readOnly />
        <span>全部</span>
      </div>
      {options.map(opt => (
        <div
          key={opt}
          className={`ms-option ${value.includes(opt) ? 'ms-checked' : ''}`}
          onClick={(e) => toggle(e, opt)}
        >
          <input type="checkbox" checked={value.includes(opt)} readOnly />
          <span>{opt}</span>
        </div>
      ))}
    </div>
  ) : null

  return (
    <div className="ms-wrapper">
      <div
        className={`ms-trigger ${open ? 'ms-open' : ''}`}
        ref={triggerRef}
        onClick={(e) => { e.stopPropagation(); setOpen(prev => !prev) }}
      >
        <span className={allSelected ? 'ms-placeholder' : ''}>{displayText}</span>
        <span className="ms-arrow">{open ? '▲' : '▼'}</span>
      </div>
      {dropdownEl && createPortal(dropdownEl, document.body)}
    </div>
  )
}

// --- Auth Modal ---
function AuthModal({ onLogin, onClose }) {
  const [isLogin, setIsLogin] = useState(true)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      console.log('发送请求:', isLogin ? '/auth/login' : '/auth/register', { username })
      const endpoint = isLogin ? '/auth/login' : '/auth/register'
      const data = await api(endpoint, {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      })
      console.log('收到响应:', data)
      if (data?.error) {
        setError(data.error)
      } else if (data?.token) {
        setToken(data.token)
        onLogin({ user_id: data.user_id, username: data.username, role: data.role || 'user' })
      } else {
        setError('未知错误')
      }
    } catch (err) {
      console.error('请求错误:', err)
      setError(err.message || '请求失败，请稍后重试')
    }
    setLoading(false)
  }

  return (
    <div className="mo" onClick={onClose}>
      <div className="md" onClick={e => e.stopPropagation()} style={{ minWidth: 320 }}>
        <h3>{isLogin ? '登录' : '注册'}</h3>
        <form onSubmit={handleSubmit}>
          <div className="mg">
            <label>用户名</label>
            <input
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder="输入用户名"
              required
              minLength={2}
              maxLength={50}
            />
          </div>
          <div className="mg">
            <label>密码</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="输入密码"
              required
              minLength={4}
            />
          </div>
          {error && <div className="error-msg" style={{ color: '#ff4444', marginBottom: 12 }}>{error}</div>}
          <div className="ma">
            <button type="button" className="btn btn-c" onClick={onClose}>取消</button>
            <button type="submit" className="btn" disabled={loading}>
              {loading ? '处理中...' : (isLogin ? '登录' : '注册')}
            </button>
          </div>
        </form>
        <div style={{ marginTop: 16, textAlign: 'center' }}>
          {isLogin ? (
            <span style={{ color: 'var(--text-dim)' }}>没有账号？ <a href="#" onClick={(e) => { e.preventDefault(); setIsLogin(false) }}>立即注册</a></span>
          ) : (
            <span style={{ color: 'var(--text-dim)' }}>已有账号？ <a href="#" onClick={(e) => { e.preventDefault(); setIsLogin(true) }}>立即登录</a></span>
          )}
        </div>
      </div>
    </div>
  )
}

// --- Item Form Modal ---
function ItemForm({ item, onSave, onClose, chars, types, seasons }) {
  const [form, setForm] = useState(item || {
    type: types?.[0] || '人格', identity_name: '', season: seasons?.[0] || '常驻', character: chars?.[0] || '李箱', rarity: 3, owned: 0,
  })

  return (
    <div className="mo" onClick={onClose}>
      <div className="md" onClick={e => e.stopPropagation()}>
        <h3>{item ? '编辑人格/E.G.O' : '添加人格/E.G.O'}</h3>
        <div className="mg">
          <label>类型</label>
          <select value={form.type} onChange={e => setForm({ ...form, type: e.target.value })}>
            {(types || ['人格', 'E.G.O']).map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div className="mg">
          <label>人格/EGO 名称</label>
          <input value={form.identity_name} onChange={e => setForm({ ...form, identity_name: e.target.value })} />
        </div>
        <div className="mg">
          <label>角色</label>
          <select value={form.character} onChange={e => setForm({ ...form, character: e.target.value })}>
            {(chars || DEFAULT_CHARS).map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div className="mg">
          <label>稀有度</label>
          <select value={form.rarity} onChange={e => setForm({ ...form, rarity: +e.target.value })}>
            <option value={3}>★★★ (400碎片)</option>
            <option value={2}>★★ (150碎片)</option>
          </select>
        </div>
        <div className="mg">
          <label>赛季</label>
          <select value={form.season} onChange={e => setForm({ ...form, season: e.target.value })}>
            {(seasons || DEFAULT_SEASONS).map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="ma">
          <button className="btn btn-c" onClick={onClose}>取消</button>
          <button className="btn" onClick={() => onSave(form)}>保存</button>
        </div>
      </div>
    </div>
  )
}

// --- Calc Tab ---
function CalcTab({ chars, types, seasons, typeFilter, seasonFilter, charFilter, timeWeeks, weeklyMirror, currentBoxes, hasPass,
  setTypeFilter, setSeasonFilter, setCharFilter, setTimeWeeks, setWeeklyMirror, setCurrentBoxes, setHasPass,
  charFragments, onUpdateCharFragments, result, loading, onCalc }) {
  return (
    <>
      <div className="card">
        <h2>筛选条件</h2>
        <div className="filters">
          <MultiSelect options={types} value={typeFilter} onChange={setTypeFilter} placeholder="全部类型" />
          <MultiSelect options={seasons} value={seasonFilter} onChange={setSeasonFilter} placeholder="全部赛季" />
          <MultiSelect options={chars} value={charFilter} onChange={setCharFilter} placeholder="全部角色" />
          <div className="fg">
            <label>目前箱子数</label>
            <input type="number" value={currentBoxes} onChange={e => setCurrentBoxes(+e.target.value)} />
          </div>
          <div className="fg">
            <label>时间范围(周)</label>
            <input type="number" value={timeWeeks} onChange={e => setTimeWeeks(+e.target.value)} />
          </div>
          <div className="fg">
            <label>每周普牢次数</label>
            <input type="number" value={weeklyMirror} onChange={e => setWeeklyMirror(+e.target.value)} />
          </div>
          <div className="fg">
            <label>
              <input type="checkbox" checked={hasPass} onChange={e => setHasPass(e.target.checked)} />
              是否有通行证
            </label>
          </div>
          <button className="btn" onClick={onCalc} disabled={loading}>
            {loading ? '计算中...' : '重新计算'}
          </button>
        </div>
      </div>
      {/* 角色碎片持有输入 */}
      <div className="card">
        <h2>持有碎片（各角色已拥有碎片数）</h2>
        <div className="char-fragments-grid">
          {chars.map(ch => (
            <div key={ch} className="cf-item">
              <label>{ch}</label>
              <input
                type="number"
                min="0"
                value={charFragments[ch] || ''}
                onChange={e => {
                  const val = e.target.value === '' ? 0 : parseInt(e.target.value) || 0
                  onUpdateCharFragments({ ...charFragments, [ch]: val })
                }}
                placeholder="0"
              />
            </div>
          ))}
        </div>
      </div>
      {result && (
        <>
          <div className="stats-row">
            <div className="sc"><div className="l">总箱子缺口</div><div className="v gold">{result.total_box_gap}</div></div>
            <div className="sc"><div className="l">剩余缺口(扣除已有箱子)</div><div className="v red">{result.remaining_gap}</div></div>
            <div className="sc"><div className="l">每周需普牢(基于{timeWeeks}周)</div><div className="v green">{result.weekly_mirror_needed} 次</div></div>
            <div className="sc"><div className="l">所需周数(基于{weeklyMirror}次/周)</div><div className="v green">{result.weeks_needed} 周</div></div>
          </div>
          <div className="card">
            <h2>每周箱子来源</h2>
            <div className="sg">
              <div className="si"><span className="sl">每日任务({hasPass ? '21' : '7'}/周)</span><span className="sv">{result.weekly_sources.daily_mission}</span></div>
              <div className="si"><span className="sl">每周任务</span><span className="sv">{result.weekly_sources.weekly_mission}</span></div>
              <div className="si"><span className="sl">困难加成镜牢</span><span className="sv">{result.weekly_sources.hard_mirror}</span></div>
              <div className="si"><span className="sl">普通镜牢({weeklyMirror}次/周)</span><span className="sv">{result.weekly_sources.regular_mirror}</span></div>
            </div>
          </div>
          <div className="card">
            <h2>各角色缺口明细</h2>
            <div style={{ maxHeight: 'none', overflow: 'visible' }}>
              <table>
                <thead>
                  <tr><th>角色</th><th>目标碎片</th><th>持有碎片</th><th>碎片缺口</th><th>箱子缺口</th></tr>
                </thead>
                <tbody>
                  {result.characters.filter(c => c.box_gap > 0).map(c => (
                    <tr key={c.character}>
                      <td className="cn">{c.character}</td>
                      <td>{c.target_fragments}</td>
                      <td>{c.owned_fragments || 0}</td>
                      <td>{c.fragment_gap}</td>
                      <td>{c.box_gap}</td>
                    </tr>
                  ))}
                  <tr className="sum-row">
                    <td className="cn">合计</td>
                    <td>{result.characters.reduce((s, c) => s + c.target_fragments, 0)}</td>
                    <td>{result.characters.reduce((s, c) => s + (c.owned_fragments || 0), 0)}</td>
                    <td>{result.characters.reduce((s, c) => s + c.fragment_gap, 0)}</td>
                    <td>{result.total_box_gap}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
      {!result && (
        <div className="card"><p style={{ color: 'var(--text-dim)', textAlign: 'center', padding: 40 }}>点击"重新计算"查看结果</p></div>
      )}
    </>
  )
}

// --- Items Tab ---
// ownedIds: { itemId: true, itemId: true, ... } JSON格式
function ItemsTab({ items, ownedIds, wishIds, onRefresh, onUpdateItem, onBatchUpdate, onBatchWish, onUpdateWish, chars, types, seasons }) {
  const [search, setSearch] = useState('')
  const [filterType, setFilterType] = useState([])
  const [filterSeason, setFilterSeason] = useState([])
  const [filterChar, setFilterChar] = useState([])
  const [showForm, setShowForm] = useState(false)
  const [editItem, setEditItem] = useState(null)
  const [saving, setSaving] = useState(false)
  const [sortKey, setSortKey] = useState('id')
  const [sortAsc, setSortAsc] = useState(true)

  // 判断人格/E.G.O是否持有
  const isOwned = (itemId) => !!ownedIds[itemId]
  // 判断人格/E.G.O是否想要
  const isWish = (itemId) => !!wishIds[itemId]

  // 排序函数
  const handleSort = (key) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc)
    } else {
      setSortKey(key)
      setSortAsc(true)
    }
  }

  const getSortIcon = (key) => {
    if (sortKey !== key) return ''
    return sortAsc ? ' ▲' : ' ▼'
  }

  const filtered = [...items]
    .filter(it => {
    if (filterType.length > 0 && !filterType.includes(it.type)) return false
    if (filterSeason.length > 0 && !filterSeason.includes(it.season)) return false
    if (filterChar.length > 0 && !filterChar.includes(it.character)) return false
    if (search) {
      const q = search.toLowerCase()
      if (!it.identity_name.toLowerCase().includes(q) && !it.character.toLowerCase().includes(q)) return false
    }
    return true
  })
    .sort((a, b) => {
      let valA, valB
      switch (sortKey) {
        case 'type': valA = a.type; valB = b.type; break
        case 'name': valA = a.identity_name; valB = b.identity_name; break
        case 'character': valA = a.character; valB = b.character; break
        case 'rarity': valA = a.rarity; valB = b.rarity; break
        case 'season': valA = a.season; valB = b.season; break
        case 'fragments': valA = a.fragments_needed; valB = b.fragments_needed; break
        case 'boxes': valA = a.boxes_needed; valB = b.boxes_needed; break
        default: valA = a.id; valB = b.id
      }
      if (typeof valA === 'string') {
        return sortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA)
      }
      return sortAsc ? valA - valB : valB - valA
    })

  const ownedCount = Object.keys(ownedIds).length
  const allVisibleOwned = filtered.length > 0 && filtered.every(i => isOwned(i.id))
  const allVisibleWish = filtered.length > 0 && filtered.every(i => isWish(i.id))

  const toggleOwned = useCallback(async (id) => {
    const currentlyOwned = isOwned(id)
    await onUpdateItem(id, !currentlyOwned)
    onRefresh()
  }, [ownedIds, onUpdateItem, onRefresh])

  const toggleWish = useCallback(async (id) => {
    const currentlyWish = isWish(id)
    await onUpdateWish(id, !currentlyWish)
    onRefresh()
  }, [wishIds, onUpdateWish, onRefresh])

  const batchSet = useCallback(async (owned) => {
    if (!filtered.length) return
    setSaving(true)
    try {
      const ids = filtered.map(i => i.id)
      await onBatchUpdate(ids, owned)
      onRefresh()
    } finally { setSaving(false) }
  }, [filtered, onBatchUpdate, onRefresh])

  const batchToggle = useCallback(async () => {
    if (!filtered.length) return
    setSaving(true)
    try {
      const ownedList = filtered.filter(i => isOwned(i.id)).map(i => i.id)
      const unownedList = filtered.filter(i => !isOwned(i.id)).map(i => i.id)
      if (ownedList.length) await onBatchUpdate(ownedList, false)
      if (unownedList.length) await onBatchUpdate(unownedList, true)
      onRefresh()
    } finally { setSaving(false) }
  }, [filtered, onRefresh, onBatchUpdate])

  const batchSetWish = useCallback(async (wish) => {
    if (!filtered.length) return
    setSaving(true)
    try {
      const ids = filtered.map(i => i.id)
      await onBatchWish(ids, wish)
      onRefresh()
    } finally { setSaving(false) }
  }, [filtered, onBatchWish, onRefresh])

  const handleSave = useCallback(async (form) => {
    setSaving(true)
    try {
      if (editItem) {
        await api('/items/' + editItem.id, { method: 'PUT', body: JSON.stringify(form) })
      } else {
        await api('/items', { method: 'POST', body: JSON.stringify(form) })
      }
      setShowForm(false)
      setEditItem(null)
      onRefresh()
    } finally { setSaving(false) }
  }, [editItem, onRefresh])

  const handleDelete = useCallback(async (id) => {
    if (!confirm('确定删除？')) return
    await api('/items/' + id, { method: 'DELETE' })
    onRefresh()
  }, [onRefresh])

  const isAdmin = window.__userRole === 'admin'

  return (
    <div className="card">
      <div className="ih">
        <h2>人格/E.G.O列表 ({items.length} 个 | 已拥有 {ownedCount} | 未拥有 {items.length - ownedCount})</h2>
        {isAdmin && <button className="btn" onClick={() => { setEditItem(null); setShowForm(true) }}>添加人格/E.G.O</button>}
      </div>
      <div className="toolbar">
        <input className="search-input" placeholder="搜索名称/角色..." value={search} onChange={e => setSearch(e.target.value)} />
        <MultiSelect options={types} value={filterType} onChange={setFilterType} placeholder="全部类型" />
        <MultiSelect options={seasons} value={filterSeason} onChange={setFilterSeason} placeholder="全部赛季" />
        <MultiSelect options={chars} value={filterChar} onChange={setFilterChar} placeholder="全部角色" />
        <span className="fc">显示 {filtered.length} 个</span>
      </div>
      {isAdmin && (
        <div className="batch-bar">
          <span>批量操作 (当前列表):</span>
          <button className="btn btn-sm btn-s" onClick={() => batchSet(true)} disabled={saving || !filtered.length}>全部标为已拥有</button>
          <button className="btn btn-sm btn-s" onClick={() => batchSet(false)} disabled={saving || !filtered.length}>全部标为未拥有</button>
          <button className="btn btn-sm btn-s" onClick={batchToggle} disabled={saving || !filtered.length}>已拥有/未拥有互换</button>
        </div>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th style={{ width: 80 }}>
                <input type="checkbox" checked={allVisibleOwned && filtered.length > 0}
                  onChange={e => batchSet(e.target.checked)} title="全选/全不选当前列表" />
                <span style={{ marginLeft: 4 }}>持有</span>
              </th>
              <th style={{ width: 80, textAlign: 'center', cursor: 'pointer' }} onClick={() => batchSetWish(!allVisibleWish)} title="全选/取消当前列表想要">
                <span style={{ fontSize: 20, color: allVisibleWish ? '#f59e0b' : '#ccc' }}>★</span>
                <span style={{ marginLeft: 4 }}>想要</span>
              </th>
              <th style={{ cursor: 'pointer' }} onClick={() => handleSort('type')}>类型{getSortIcon('type')}</th>
              <th style={{ cursor: 'pointer' }} onClick={() => handleSort('name')}>名称{getSortIcon('name')}</th>
              <th style={{ cursor: 'pointer' }} onClick={() => handleSort('character')}>角色{getSortIcon('character')}</th>
              <th style={{ cursor: 'pointer' }} onClick={() => handleSort('rarity')}>稀有度{getSortIcon('rarity')}</th>
              <th style={{ cursor: 'pointer' }} onClick={() => handleSort('season')}>赛季{getSortIcon('season')}</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(it => (
              <tr key={it.id} style={{ opacity: isOwned(it.id) ? 0.45 : 1 }}>
                <td><input type="checkbox" checked={isOwned(it.id)} onChange={() => toggleOwned(it.id)} /></td>
                <td style={{ textAlign: 'center' }}><span style={{ cursor: 'pointer', fontSize: 20, color: isWish(it.id) ? '#f59e0b' : '#ccc', display: 'inline-block', padding: '4px 8px' }} onClick={() => toggleWish(it.id)} title="想要">★</span></td>
                <td>{it.type}</td>
                <td style={{ textAlign: 'left' }}>{it.identity_name}</td>
                <td>{it.character}</td>
                <td><Stars n={it.rarity} /></td>
                <td>{it.season}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={7} style={{ color: 'var(--text-dim)', textAlign: 'center', padding: 20 }}>没有匹配的人格/E.G.O</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {showForm && <ItemForm item={editItem} onSave={handleSave} onClose={() => { setShowForm(false); setEditItem(null) }} chars={chars} types={types} seasons={seasons} />}
    </div>
  )
}

// --- Main App ---
export default function App() {
  const [tab, setTab] = useState('calc')
  const [user, setUser] = useState(null)  // 当前登录用户
  const [showAuth, setShowAuth] = useState(false)
  const [isGuestMode, setIsGuestMode] = useState(false)  // 游客模式
  const [items, setItems] = useState([])  // 基础人格/E.G.O数据
  const [ownedIds, setOwnedIds] = useState({})  // 持有的人格/E.G.OID JSON: {1: true, 5: true}
  const [wishIds, setWishIds] = useState({})  // 想要的人格/E.G.OID JSON: {1: true, 5: true}
  const [charFragments, setCharFragments] = useState({})  // 各角色持有的碎片数: { "李箱": 100, "浮士德": 50 }
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [typeFilter, setTypeFilter] = useState([])
  const [seasonFilter, setSeasonFilter] = useState([])
  const [charFilter, setCharFilter] = useState([])
  const [timeWeeks, setTimeWeeks] = useState(10)
  const [weeklyMirror, setWeeklyMirror] = useState(10)
  const [currentBoxes, setCurrentBoxes] = useState(195)
  const [hasPass, setHasPass] = useState(true)
  const [apiError, setApiError] = useState(false)

  // 常量（从数据库加载）
  const [chars, setChars] = useState(DEFAULT_CHARS)
  const [types, setTypes] = useState(DEFAULT_TYPES)
  const [seasons, setSeasons] = useState(DEFAULT_SEASONS)

  // 检查登录状态
  useEffect(() => {
    const token = getToken()
    if (token) {
      api('/auth/me').then(data => {
        if (data?.user_id) {
          setUser({ user_id: data.user_id, username: data.username })
        } else {
          removeToken()
        }
      }).catch(() => removeToken())
    }
  }, [])

  // 加载基础人格/E.G.O数据
  const loadItems = useCallback(async () => {
    const newItems = await api('/items')
    if (newItems) setItems(newItems)
    return newItems
  }, [])

  // 加载用户持有的人格/E.G.OID（从后端获取owned_ids和wish_ids JSON）
  const loadOwnedIds = useCallback(async () => {
    const token = getToken()  // 实时获取token
    if (token) {
      // 登录用户：从后端获取
      try {
        const userItems = await api('/user/items')
        if (userItems) {
          const ids = {}
          const wishes = {}
          userItems.forEach(it => {
            if (it.owned) ids[it.id] = true
            if (it.wish) wishes[it.id] = true
          })
          setOwnedIds(ids)
          setWishIds(wishes)
        }
      } catch (e) {
        // 忽略401错误
        console.log('loadOwnedIds跳过:', e.message)
      }
    } else if (isGuestMode) {
      // 游客：从localStorage加载
      const stored = localStorage.getItem('guest_owned_ids')
      if (stored) {
        try {
          setOwnedIds(JSON.parse(stored))
        } catch {}
      }
      const storedWish = localStorage.getItem('guest_wish_ids')
      if (storedWish) {
        try {
          setWishIds(JSON.parse(storedWish))
        } catch {}
      }
    }
  }, [isGuestMode])

  // 加载用户设置
  const loadUserSettings = useCallback(async () => {
    const token = getToken()  // 实时获取token，避免闭包问题
    if (token) {
      // 登录用户：从后端获取
      try {
        const settings = await api('/user/settings')
        if (settings) {
          setTimeWeeks(settings.time_weeks || 10)
          setWeeklyMirror(settings.weekly_mirror_count || 10)
          setCurrentBoxes(settings.current_boxes ?? 195)
          // 确保转换为布尔类型
          setHasPass(settings.has_pass !== undefined ? Boolean(settings.has_pass) : true)
        }
      } catch (e) {
        // 忽略401错误（未登录或token失效）
        console.log('loadUserSettings跳过:', e.message)
      }
    } else if (isGuestMode) {
      // 游客：从localStorage加载
      const stored = localStorage.getItem('guest_settings')
      if (stored) {
        try {
          const settings = JSON.parse(stored)
          setTimeWeeks(settings.time_weeks || 10)
          setWeeklyMirror(settings.weekly_mirror_count || 10)
          setCurrentBoxes(settings.current_boxes ?? 195)
          // 确保转换为布尔类型
          setHasPass(settings.has_pass !== undefined ? Boolean(settings.has_pass) : true)
        } catch {}
      }
    }
  }, [isGuestMode])

  // 加载用户持有的角色碎片
  const loadCharFragments = useCallback(async () => {
    const token = getToken()
    if (token) {
      // 登录用户：从后端获取
      try {
        const frags = await api('/user/fragments')
        if (frags) {
          setCharFragments(frags)
        }
      } catch (e) {
        console.log('loadCharFragments跳过:', e.message)
      }
    } else if (isGuestMode) {
      // 游客：从localStorage加载
      const stored = localStorage.getItem('guest_char_fragments')
      if (stored) {
        try {
          setCharFragments(JSON.parse(stored))
        } catch {}
      }
    }
  }, [isGuestMode])

  // 保存用户持有的角色碎片
  const saveCharFragments = useCallback(async (newFrags) => {
    setCharFragments(newFrags)
    const token = getToken()
    if (token) {
      // 登录用户：保存到后端
      await api('/user/fragments', {
        method: 'PUT',
        body: JSON.stringify(newFrags),
      })
    } else if (isGuestMode) {
      // 游客：保存到localStorage
      localStorage.setItem('guest_char_fragments', JSON.stringify(newFrags))
    }
  }, [isGuestMode])

  // 加载数据
  const loadData = useCallback(async () => {
    try {
      // 加载常量（角色、类型、赛季）
      const constants = await api('/constants')
      if (constants) {
        if (constants.characters?.length) setChars(constants.characters)
        if (constants.types?.length) setTypes(constants.types)
        if (constants.seasons?.length) setSeasons(constants.seasons)
      }
      
      // 加载基础人格/E.G.O
      await loadItems()
      
      // 加载全局设置（默认值）
      const globalSettings = await api('/settings')
      if (globalSettings) {
        setTimeWeeks(globalSettings.time_weeks || 10)
        setWeeklyMirror(globalSettings.weekly_mirror_count || 10)
        setCurrentBoxes(globalSettings.current_boxes ?? 195)
        // 确保转换为布尔类型，避免 checkbox 接收字符串 "true"
        setHasPass(globalSettings.has_pass !== undefined ? Boolean(globalSettings.has_pass) : true)
      }
      
      // 加载用户个人设置（覆盖全局设置）
      await loadUserSettings()
      
      // 加载持有的人格/E.G.OID
      await loadOwnedIds()

      // 加载用户持有的角色碎片
      await loadCharFragments()

      setApiError(false)
    } catch {
      setApiError(true)
    }
  }, [isGuestMode, loadItems, loadUserSettings, loadOwnedIds, loadCharFragments])

  useEffect(() => { loadData() }, [loadData])

  // 监听游客模式变化，自动加载数据并计算
  useEffect(() => {
    console.log('[useEffect] isGuestMode changed:', isGuestMode)
    if (isGuestMode) {
      console.log('[useEffect] loading data and calc')
      // 使用 ref 获取最新的 calc 函数
      loadData().then(() => calcRef.current())
    }
  }, [isGuestMode, loadData])

  const calc = useCallback(async () => {
    console.log('[calc] called, user:', !!user, 'isGuestMode:', isGuestMode)
    setLoading(true)
    try {
      let r
      const commonParams = {
        type_filter: typeFilter.length ? typeFilter : 'ALL',
        season_filter: seasonFilter.length ? seasonFilter : 'ALL',
        character_filter: charFilter.length ? charFilter : 'ALL',
        time_weeks: timeWeeks,
        weekly_mirror_count: weeklyMirror,
        current_boxes: currentBoxes,
        has_pass: hasPass,
      }
      
      if (user) {
        console.log('[calc] Using /user/calculate API')
        // 登录用户计算API（后端从数据库读取owned_ids和wish_ids）
        r = await api('/user/calculate', {
          method: 'POST',
          body: JSON.stringify(commonParams),
        })
      } else if (isGuestMode) {
        console.log('[calc] Using /guest/calculate API')
        // 游客计算API：传入owned_ids和wish_ids JSON
        r = await api('/guest/calculate', {
          method: 'POST',
          body: JSON.stringify({
            ...commonParams,
            owned_ids: ownedIds,
            wish_ids: wishIds,
            character_fragments: charFragments,
          }),
        })
      } else {
        console.log('[calc] Using /calculate API (public)')
        // 公共计算API（无用户数据）：也传递 owned_ids 和 wish_ids
        r = await api('/calculate', {
          method: 'POST',
          body: JSON.stringify({
            ...commonParams,
            owned_ids: ownedIds,
            wish_ids: wishIds,
            character_fragments: charFragments,
          }),
        })
      }
      if (r) setResult(r)
    } catch (e) { console.error(e) }
    setLoading(false)
  }, [user, isGuestMode, ownedIds, wishIds, charFragments, typeFilter, seasonFilter, charFilter, timeWeeks, weeklyMirror, currentBoxes, hasPass])

  // 用 ref 保存 calc 函数的最新版本，确保 useEffect 中调用的是最新版本
  const calcRef = useRef(calc)
  calcRef.current = calc

  const switchTab = useCallback((t) => {
    setTab(t)
    if (t === 'calc') calc()
  }, [calc])

  const handleLogin = (userData) => {
    setUser(userData)
    window.__userRole = userData.role || 'user'
    setShowAuth(false)
    setIsGuestMode(false)
    // 登录后重新加载用户数据
    loadData()
  }

  const handleLogout = () => {
    removeToken()
    setUser(null)
    setIsGuestMode(false)
    window.__userRole = null
    setOwnedIds({})
    setResult(null)
    // 重新加载公共数据
    loadData()
  }

  const handleSaveSettings = useCallback((newTimeWeeks, newWeeklyMirror, newCurrentBoxes, newHasPass) => {
    const token = getToken()
    const settingsData = {
      time_weeks: newTimeWeeks !== undefined ? newTimeWeeks : timeWeeks,
      weekly_mirror_count: newWeeklyMirror !== undefined ? newWeeklyMirror : weeklyMirror,
      current_boxes: newCurrentBoxes !== undefined ? newCurrentBoxes : currentBoxes,
      has_pass: newHasPass !== undefined ? newHasPass : hasPass,
    }
    
    if (token) {
      api('/user/settings', {
        method: 'POST',
        body: JSON.stringify(settingsData),
      })
    } else if (isGuestMode) {
      localStorage.setItem('guest_settings', JSON.stringify(settingsData))
    }
  }, [timeWeeks, weeklyMirror, currentBoxes, hasPass, isGuestMode])

  const handleRefreshUserItems = () => {
    loadOwnedIds()
  }

  // 更新人格/E.G.O持有状态（切换owned）
  const updateOwned = async (itemId, owned) => {
    const newOwnedIds = { ...ownedIds }
    if (owned) {
      newOwnedIds[itemId] = true
    } else {
      delete newOwnedIds[itemId]
    }
    setOwnedIds(newOwnedIds)
    
    // 保存到后端或本地
    if (user) {
      // 登录用户：保存到后端（只传owned，不传wish）
      await api('/user/items/' + itemId, { 
        method: 'PUT', 
        body: JSON.stringify({ owned: owned ? 1 : 0 }) 
      })
    } else if (isGuestMode) {
      // 游客：保存到localStorage
      localStorage.setItem('guest_owned_ids', JSON.stringify(newOwnedIds))
    }
  }

  // 批量更新人格/E.G.O持有状态
  const batchUpdateOwned = async (itemIds, owned) => {
    const newOwnedIds = { ...ownedIds }
    if (owned) {
      itemIds.forEach(id => { newOwnedIds[id] = true })
    } else {
      itemIds.forEach(id => { delete newOwnedIds[id] })
    }
    setOwnedIds(newOwnedIds)
    
    // 保存到后端或本地
    if (user) {
      // 登录用户：批量保存到后端
      await api('/user/items/batch-owned', { 
        method: 'PUT', 
        body: JSON.stringify({ ids: itemIds, owned: owned ? 1 : 0 }) 
      })
    } else if (isGuestMode) {
      // 游客：保存到localStorage
      localStorage.setItem('guest_owned_ids', JSON.stringify(newOwnedIds))
    }
  }

  // 批量更新人格/E.G.O想要状态
  const batchUpdateWish = async (itemIds, wish) => {
    const newWishIds = { ...wishIds }
    if (wish) {
      itemIds.forEach(id => { newWishIds[id] = true })
    } else {
      itemIds.forEach(id => { delete newWishIds[id] })
    }
    setWishIds(newWishIds)
    
    // 保存到后端或本地
    if (user) {
      // 登录用户：批量保存到后端
      await api('/user/items/batch-owned', { 
        method: 'PUT', 
        body: JSON.stringify({ ids: itemIds, wish: wish ? 1 : 0 }) 
      })
    } else if (isGuestMode) {
      // 游客：保存到localStorage
      localStorage.setItem('guest_wish_ids', JSON.stringify(newWishIds))
    }
  }

  // 更新人格/E.G.O想要状态（切换wish）
  const updateWish = async (itemId, wish) => {
    const newWishIds = { ...wishIds }
    if (wish) {
      newWishIds[itemId] = true
    } else {
      delete newWishIds[itemId]
    }
    setWishIds(newWishIds)
    
    // 保存到后端或本地
    if (user) {
      // 登录用户：保存到后端（只传wish，不传owned）
      await api('/user/items/' + itemId, { 
        method: 'PUT', 
        body: JSON.stringify({ wish: wish ? 1 : 0 }) 
      })
    } else if (isGuestMode) {
      // 游客：保存到localStorage
      localStorage.setItem('guest_wish_ids', JSON.stringify(newWishIds))
    }
  }

  return (
    <div className="app-root">
      <h1>边狱巴士 - 箱子缺口计算器
        <span className="db-badge">MySQL</span>
        {user && <span className="db-badge" style={{ background: '#4CAF50' }}>用户: {user.username}</span>}
      </h1>
      {apiError && (
        <div className="api-warn">后端服务未连接，请先启动 server.py（python server.py）</div>
      )}
      {/* 用户栏 */}
      <div className="user-bar">
        {user ? (
          <>
            <span>欢迎，{user.username}</span>
            <button className="btn btn-sm" onClick={handleLogout}>退出登录</button>
          </>
        ) : (
          <>
            <button className="btn btn-sm" onClick={() => setShowAuth(true)}>登录/注册</button>
            <button id="guest-mode-btn" className="btn btn-sm btn-c" onClick={() => { console.log('[Button] Guest mode clicked, current isGuestMode:', isGuestMode); setIsGuestMode(true) }}>游客模式</button>
            {isGuestMode && <span style={{ color: 'var(--text-dim)', fontSize: 12 }}>（游客模式，数据不保存）</span>}
          </>
        )}
      </div>
      {showAuth && <AuthModal onLogin={handleLogin} onClose={() => setShowAuth(false)} />}
      <div className="tabs">
        <div className={`tab ${tab === 'calc' ? 'active' : ''}`} onClick={() => switchTab('calc')}>缺口计算</div>
        <div className={`tab ${tab === 'items' ? 'active' : ''}`} onClick={() => setTab('items')}>人格/E.G.O管理</div>
      </div>
      <div className="fade-in">
        {tab === 'calc' ? (
          <CalcTab
            chars={chars} types={types} seasons={seasons}
            typeFilter={typeFilter} seasonFilter={seasonFilter} charFilter={charFilter}
            timeWeeks={timeWeeks} weeklyMirror={weeklyMirror} currentBoxes={currentBoxes} hasPass={hasPass}
            setTypeFilter={setTypeFilter} setSeasonFilter={setSeasonFilter} setCharFilter={setCharFilter}
            setTimeWeeks={(v) => { setTimeWeeks(v); handleSaveSettings(v, undefined, undefined, undefined) }}
            setWeeklyMirror={(v) => { setWeeklyMirror(v); handleSaveSettings(undefined, v, undefined, undefined) }}
            setCurrentBoxes={(v) => { setCurrentBoxes(v); handleSaveSettings(undefined, undefined, v, undefined) }}
            setHasPass={(v) => { setHasPass(v); handleSaveSettings(undefined, undefined, undefined, v) }}
            charFragments={charFragments} onUpdateCharFragments={saveCharFragments}
            result={result} loading={loading} onCalc={calc}
          />
        ) : (
          <ItemsTab
            chars={chars} types={types} seasons={seasons}
            items={items}
            ownedIds={ownedIds}
            wishIds={wishIds}
            onRefresh={handleRefreshUserItems}
            onUpdateItem={updateOwned}
            onBatchUpdate={batchUpdateOwned}
            onBatchWish={batchUpdateWish}
            onUpdateWish={updateWish}
          />
        )}
      </div>
    </div>
  )
}
