'use client';

import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, AreaChart, Area
} from 'recharts';

const API_BASE_URL = 'http://localhost:8001/api';

export default function Home() {
  const [summary, setSummary] = useState<any>(null);
  const [indicators, setIndicators] = useState<any[]>([]);
  const [territories, setTerritories] = useState<any[]>([]);
  const [selectedIndicator, setSelectedIndicator] = useState('10108000001');
  const [selectedTerritory, setSelectedTerritory] = useState('020');
  const [facts, setFacts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any>(null);
  
  // Advanced features state
  const [chartType, setChartType] = useState<'line' | 'bar' | 'area'>('line');
  const [yearRange, setYearRange] = useState<[number, number]>([1990, 2025]);
  const [tableFilter, setTableFilter] = useState('');
  const [selectedRegionFilter, setSelectedRegionFilter] = useState('all');

  useEffect(() => {
    fetchInitialData();
  }, []);

  useEffect(() => {
    if (selectedIndicator) {
      fetchFacts();
    }
  }, [selectedIndicator, selectedTerritory]);

  const fetchInitialData = async () => {
    try {
      setLoading(true);
      const [summaryRes, indicatorsRes, territoriesRes] = await Promise.all([
        axios.get(`${API_BASE_URL}/stats/summary`),
        axios.get(`${API_BASE_URL}/indicators`),
        axios.get(`${API_BASE_URL}/territories`)
      ]);

      setSummary(summaryRes.data.data);
      setIndicators(indicatorsRes.data.data);
      setTerritories(territoriesRes.data.data);
      if (indicatorsRes.data.data.length > 0) {
        setSelectedIndicator(indicatorsRes.data.data[0].indicator_code || indicatorsRes.data.data[0].code);
      }
      setLoading(false);
    } catch (error) {
      console.error('Error fetching initial data:', error);
      setLoading(false);
    }
  };

  const fetchFacts = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/facts`, {
        params: { 
          indicator_code: selectedIndicator,
          geo_code: selectedTerritory === 'all' ? undefined : selectedTerritory,
          limit: 500 
        }
      });
      const sorted = (response.data.data || []).sort((a: any, b: any) => (a.year || 0) - (b.year || 0));
      setFacts(sorted);
    } catch (error) {
      console.error('Error fetching facts:', error);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;

    try {
      const response = await axios.get(`${API_BASE_URL}/search`, {
        params: { q: searchQuery }
      });
      setSearchResults(response.data.data);
    } catch (error) {
      console.error('Error searching:', error);
    }
  };

  // Filtered facts based on year range & text filter
  const filteredFacts = useMemo(() => {
    return facts.filter(f => {
      const matchYear = f.year >= yearRange[0] && f.year <= yearRange[1];
      const matchText = tableFilter === '' || 
        (f.geo_name_ru && f.geo_name_ru.toLowerCase().includes(tableFilter.toLowerCase())) ||
        (f.breakdown_value_ru && f.breakdown_value_ru.toLowerCase().includes(tableFilter.toLowerCase()));
      const matchRegion = selectedRegionFilter === 'all' || f.region_name_ru === selectedRegionFilter;
      return matchYear && matchText && matchRegion;
    });
  }, [facts, yearRange, tableFilter, selectedRegionFilter]);

  // Unique regions for additional filtering
  const regionsList = useMemo(() => {
    const regs = new Set(facts.map(f => f.region_name_ru).filter(Boolean));
    return Array.from(regs);
  }, [facts]);

  const currentIndicator = indicators.find(i => (i.indicator_code || i.code) === selectedIndicator);
  const currentTerritory = territories.find(t => t.geo_code === selectedTerritory);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-slate-950 text-white">
        <div className="relative w-16 h-16 mb-4">
          <div className="absolute top-0 left-0 w-full h-full border-4 border-indigo-500/20 rounded-full"></div>
          <div className="absolute top-0 left-0 w-full h-full border-4 border-indigo-500 rounded-full animate-spin border-t-transparent"></div>
        </div>
        <p className="text-slate-400 font-semibold tracking-wide text-sm animate-pulse">Загрузка аналитической панели Белстата...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-indigo-600 selection:text-white">
      {/* Navbar */}
      <header className="bg-slate-900/90 border-b border-slate-800 sticky top-0 z-50 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-18 flex items-center justify-between">
          <div className="flex items-center space-x-3.5 py-3">
            <div className="bg-gradient-to-br from-indigo-500 to-indigo-700 text-white font-black px-3.5 py-2 rounded-2xl shadow-xl shadow-indigo-600/30 text-base tracking-wider">
              БСК
            </div>
            <div>
              <h1 className="text-sm sm:text-base font-extrabold text-white tracking-wide">Белстат: Анализ преступности</h1>
              <p className="text-xs text-slate-400 font-medium">Официальные открытые данные Республики Беларусь · 1990–2025</p>
            </div>
          </div>

          <form onSubmit={handleSearch} className="flex items-center space-x-2">
            <div className="relative">
              <input
                type="text"
                placeholder="Поиск по базе..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-slate-950/80 border border-slate-700/80 text-white placeholder-slate-500 text-xs sm:text-sm rounded-xl px-4 py-2.5 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 w-44 sm:w-72 transition shadow-inner"
              />
            </div>
            <button
              type="submit"
              className="bg-indigo-600 hover:bg-indigo-500 text-white text-xs sm:text-sm font-semibold px-4 py-2.5 rounded-xl transition shadow-lg shadow-indigo-600/30 active:scale-95"
            >
              Найти
            </button>
          </form>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 w-full space-y-8">
        
        {/* Search Results Modal / Card */}
        {searchResults && (
          <div className="bg-slate-900/90 border border-indigo-500/40 rounded-3xl p-6 shadow-2xl relative backdrop-blur-lg animate-in fade-in duration-300">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-sm font-bold text-indigo-400 uppercase tracking-widest">Результаты поиска: "{searchQuery}"</h2>
              <button 
                onClick={() => setSearchResults(null)}
                className="text-slate-400 hover:text-white text-xs font-semibold bg-slate-800 px-3 py-1.5 rounded-xl transition hover:bg-slate-700"
              >
                ✕ Закрыть
              </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h3 className="text-xs font-bold text-slate-400 mb-3 uppercase tracking-wider">Показатели ({searchResults.indicators.length})</h3>
                <div className="space-y-2 max-h-56 overflow-y-auto pr-2 custom-scrollbar">
                  {searchResults.indicators.map((ind: any) => (
                    <div 
                      key={ind.code}
                      onClick={() => { setSelectedIndicator(ind.code); setSearchResults(null); }}
                      className="bg-slate-950 hover:bg-indigo-950/40 p-3.5 rounded-2xl border border-slate-800 hover:border-indigo-500/50 cursor-pointer transition text-xs shadow-sm group"
                    >
                      <p className="font-bold text-white group-hover:text-indigo-300 transition">{ind.name_ru}</p>
                      <p className="text-slate-500 mt-1 font-mono text-[11px]">Код: {ind.code}</p>
                    </div>
                  ))}
                  {searchResults.indicators.length === 0 && <p className="text-xs text-slate-500 italic">Показатели не найдены</p>}
                </div>
              </div>
              <div>
                <h3 className="text-xs font-bold text-slate-400 mb-3 uppercase tracking-wider">Территории ({searchResults.territories.length})</h3>
                <div className="space-y-2 max-h-56 overflow-y-auto pr-2 custom-scrollbar">
                  {searchResults.territories.map((terr: any) => (
                    <div 
                      key={terr.geo_code}
                      onClick={() => { setSelectedTerritory(terr.geo_code); setSearchResults(null); }}
                      className="bg-slate-950 hover:bg-indigo-950/40 p-3.5 rounded-2xl border border-slate-800 hover:border-indigo-500/50 cursor-pointer transition text-xs shadow-sm group"
                    >
                      <p className="font-bold text-white group-hover:text-indigo-300 transition">{terr.name_ru}</p>
                      <p className="text-slate-500 mt-1 font-mono text-[11px]">Код: {terr.geo_code} | Уровень: {terr.level}</p>
                    </div>
                  ))}
                  {searchResults.territories.length === 0 && <p className="text-xs text-slate-500 italic">Территории не найдены</p>}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* KPI Summary Cards */}
        {summary && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            <div className="bg-gradient-to-b from-slate-900 to-slate-900/60 border border-slate-800/80 rounded-3xl p-6 shadow-xl relative overflow-hidden group hover:border-slate-700 transition">
              <div className="absolute top-0 right-0 w-36 h-36 bg-indigo-600/10 rounded-full blur-3xl group-hover:bg-indigo-600/20 transition"></div>
              <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Наблюдений в базе</p>
              <p className="text-3xl font-black text-white mt-3 tracking-tight">
                {summary.total_observations.toLocaleString()}
              </p>
              <p className="text-xs text-emerald-400 mt-2 font-medium flex items-center space-x-1">
                <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full inline-block"></span>
                <span>Идемпотентный сбор данных</span>
              </p>
            </div>

            <div className="bg-gradient-to-b from-slate-900 to-slate-900/60 border border-slate-800/80 rounded-3xl p-6 shadow-xl relative overflow-hidden group hover:border-slate-700 transition">
              <div className="absolute top-0 right-0 w-36 h-36 bg-purple-600/10 rounded-full blur-3xl group-hover:bg-purple-600/20 transition"></div>
              <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Показателей</p>
              <p className="text-3xl font-black text-white mt-3 tracking-tight">
                {summary.indicators_count}
              </p>
              <p className="text-xs text-slate-400 mt-2 font-medium">Раздел «Правосудие и преступность»</p>
            </div>

            <div className="bg-gradient-to-b from-slate-900 to-slate-900/60 border border-slate-800/80 rounded-3xl p-6 shadow-xl relative overflow-hidden group hover:border-slate-700 transition">
              <div className="absolute top-0 right-0 w-36 h-36 bg-blue-600/10 rounded-full blur-3xl group-hover:bg-blue-600/20 transition"></div>
              <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Территорий</p>
              <p className="text-3xl font-black text-white mt-3 tracking-tight">
                {summary.territories_count}
              </p>
              <p className="text-xs text-slate-400 mt-2 font-medium">Страна, области, 128 районов</p>
            </div>

            <div className="bg-gradient-to-b from-slate-900 to-slate-900/60 border border-slate-800/80 rounded-3xl p-6 shadow-xl relative overflow-hidden group hover:border-slate-700 transition">
              <div className="absolute top-0 right-0 w-36 h-36 bg-emerald-600/10 rounded-full blur-3xl group-hover:bg-emerald-600/20 transition"></div>
              <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Годы охвата</p>
              <p className="text-3xl font-black text-white mt-3 tracking-tight">
                {summary.years_range.min}–{summary.years_range.max}
              </p>
              <p className="text-xs text-slate-400 mt-2 font-medium">Официальная статистика Белстат</p>
            </div>
          </div>
        )}

        {/* Interactive Controls & Filters Panel */}
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 shadow-2xl space-y-6">
          <div className="flex items-center justify-between border-b border-slate-800 pb-4">
            <h2 className="text-sm font-extrabold text-white uppercase tracking-wider flex items-center space-x-2">
              <span className="w-2 h-2 bg-indigo-500 rounded-full"></span>
              <span>Параметры анализа и фильтрации</span>
            </h2>
            <button
              onClick={() => { setSelectedIndicator('10108000001'); setSelectedTerritory('020'); setYearRange([1990, 2025]); setTableFilter(''); }}
              className="text-xs text-indigo-400 hover:text-indigo-300 font-semibold transition"
            >
              Сбросить фильтры
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
            {/* Indicator Select */}
            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
                Показатель
              </label>
              <select
                value={selectedIndicator}
                onChange={(e) => setSelectedIndicator(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 text-white text-xs sm:text-sm rounded-2xl px-4 py-3 focus:outline-none focus:border-indigo-500 transition shadow-inner font-medium"
              >
                {indicators.map((ind) => (
                  <option key={ind.indicator_code || ind.code} value={ind.indicator_code || ind.code}>
                    {ind.name_ru}
                  </option>
                ))}
              </select>
            </div>

            {/* Territory Select */}
            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
                Территория
              </label>
              <select
                value={selectedTerritory}
                onChange={(e) => setSelectedTerritory(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 text-white text-xs sm:text-sm rounded-2xl px-4 py-3 focus:outline-none focus:border-indigo-500 transition shadow-inner font-medium"
              >
                <option value="020">Республика Беларусь (Всего)</option>
                {territories.filter(t => t.geo_code !== '020').map((terr) => (
                  <option key={terr.geo_code} value={terr.geo_code}>
                    {terr.name_ru} ({terr.level_name || `уровень ${terr.level}`})
                  </option>
                ))}
              </select>
            </div>

            {/* Year Range Filter */}
            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
                Годы: {yearRange[0]} — {yearRange[1]}
              </label>
              <div className="flex items-center space-x-2 pt-2">
                <input
                  type="range"
                  min="1990"
                  max="2025"
                  value={yearRange[0]}
                  onChange={(e) => setYearRange([parseInt(e.target.value), yearRange[1]])}
                  className="w-full accent-indigo-500 bg-slate-950 cursor-pointer"
                />
                <input
                  type="range"
                  min="1990"
                  max="2025"
                  value={yearRange[1]}
                  onChange={(e) => setYearRange([yearRange[0], parseInt(e.target.value)])}
                  className="w-full accent-indigo-500 bg-slate-950 cursor-pointer"
                />
              </div>
            </div>

            {/* Region Filter if applicable */}
            <div>
              <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
                Область-предок
              </label>
              <select
                value={selectedRegionFilter}
                onChange={(e) => setSelectedRegionFilter(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 text-white text-xs sm:text-sm rounded-2xl px-4 py-3 focus:outline-none focus:border-indigo-500 transition shadow-inner font-medium"
              >
                <option value="all">Все области</option>
                {regionsList.map((reg: any) => (
                  <option key={reg} value={reg}>{reg}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Data Visualization & Analytics Section */}
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-2xl space-y-6">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center border-b border-slate-800 pb-5 gap-4">
            <div>
              <h2 className="text-lg sm:text-xl font-black text-white">{currentIndicator?.name_ru || 'Статистика'}</h2>
              <p className="text-xs text-slate-400 mt-1 font-medium">
                Территория: <span className="text-indigo-400 font-bold">{currentTerritory?.name_ru || 'Республика Беларусь'}</span> · Найдено точек: <span className="text-emerald-400 font-bold">{filteredFacts.length}</span>
              </p>
            </div>
            
            <div className="flex flex-wrap items-center gap-3">
              {/* Chart Type Selector */}
              <div className="flex bg-slate-950 p-1.5 rounded-2xl border border-slate-800">
                <button
                  onClick={() => setChartType('line')}
                  className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition ${chartType === 'line' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30' : 'text-slate-400 hover:text-white'}`}
                >
                  Линия
                </button>
                <button
                  onClick={() => setChartType('bar')}
                  className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition ${chartType === 'bar' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30' : 'text-slate-400 hover:text-white'}`}
                >
                  Столбцы
                </button>
                <button
                  onClick={() => setChartType('area')}
                  className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition ${chartType === 'area' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30' : 'text-slate-400 hover:text-white'}`}
                >
                  Область
                </button>
              </div>
            </div>
          </div>

          {/* Chart Display */}
          <div className="h-96 w-full pt-4">
            <ResponsiveContainer width="100%" height="100%">
              {chartType === 'line' ? (
                <LineChart data={filteredFacts} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="year" stroke="#64748b" tick={{ fontSize: 12, fill: '#94a3b8' }} />
                  <YAxis stroke="#64748b" tick={{ fontSize: 12, fill: '#94a3b8' }} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '1rem', color: '#fff', fontSize: '12px', boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)' }}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '15px' }} />
                  <Line type="monotone" dataKey="value" name="Значение показателя" stroke="#6366f1" strokeWidth={3.5} dot={{ r: 4, fill: '#6366f1' }} activeDot={{ r: 8, stroke: '#fff', strokeWidth: 2 }} />
                </LineChart>
              ) : chartType === 'bar' ? (
                <BarChart data={filteredFacts} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="year" stroke="#64748b" tick={{ fontSize: 12, fill: '#94a3b8' }} />
                  <YAxis stroke="#64748b" tick={{ fontSize: 12, fill: '#94a3b8' }} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '1rem', color: '#fff', fontSize: '12px', boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)' }}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '15px' }} />
                  <Bar dataKey="value" name="Значение показателя" fill="#6366f1" radius={[6, 6, 0, 0]} />
                </BarChart>
              ) : (
                <AreaChart data={filteredFacts} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
                  <defs>
                    <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.8}/>
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0.0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="year" stroke="#64748b" tick={{ fontSize: 12, fill: '#94a3b8' }} />
                  <YAxis stroke="#64748b" tick={{ fontSize: 12, fill: '#94a3b8' }} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '1rem', color: '#fff', fontSize: '12px', boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)' }}
                  />
                  <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '15px' }} />
                  <Area type="monotone" dataKey="value" name="Значение показателя" stroke="#6366f1" strokeWidth={3} fillOpacity={1} fill="url(#colorValue)" />
                </AreaChart>
              )}
            </ResponsiveContainer>
          </div>
        </div>

        {/* Detailed Data Table Section */}
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 shadow-2xl space-y-6">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-slate-800 pb-5">
            <div>
              <h3 className="text-base sm:text-lg font-black text-white">Детальная таблица наблюдений</h3>
              <p className="text-xs text-slate-400 mt-0.5">Все параметры и разбивки выбранного показателя</p>
            </div>
            
            <div className="w-full sm:w-auto">
              <input
                type="text"
                placeholder="Фильтр по таблице..."
                value={tableFilter}
                onChange={(e) => setTableFilter(e.target.value)}
                className="bg-slate-950 border border-slate-800 text-white text-xs sm:text-sm rounded-xl px-4 py-2 focus:outline-none focus:border-indigo-500 w-full sm:w-64 transition shadow-inner"
              />
            </div>
          </div>

          <div className="overflow-x-auto max-h-[420px] rounded-2xl border border-slate-800/80 custom-scrollbar">
            <table className="min-w-full divide-y divide-slate-800 text-xs sm:text-sm">
              <thead className="bg-slate-950 sticky top-0 z-10 backdrop-blur-md">
                <tr>
                  <th className="px-6 py-3.5 text-left font-bold text-slate-400 uppercase tracking-wider">Год</th>
                  <th className="px-6 py-3.5 text-left font-bold text-slate-400 uppercase tracking-wider">Территория</th>
                  <th className="px-6 py-3.5 text-left font-bold text-slate-400 uppercase tracking-wider">Разбивка / Категория</th>
                  <th className="px-6 py-3.5 text-right font-bold text-slate-400 uppercase tracking-wider">Значение</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 bg-slate-900/40">
                {filteredFacts.map((fact, index) => (
                  <tr key={fact.fact_id || index} className="hover:bg-slate-800/40 transition">
                    <td className="px-6 py-4 whitespace-nowrap font-bold text-white">
                      {fact.year}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-slate-300 font-medium">
                      {fact.geo_name_ru || currentTerritory?.name_ru || 'Республика Беларусь'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-slate-400">
                      {fact.breakdown_value_ru || 'Всего'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right font-black text-indigo-400">
                      {fact.value !== null && fact.value !== undefined ? fact.value.toLocaleString() : '—'} <span className="text-slate-500 font-normal text-xs">{fact.unit_name_ru || ''}</span>
                    </td>
                  </tr>
                ))}
                {filteredFacts.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-6 py-12 text-center text-slate-500 italic">
                      Нет данных, соответствующих выбранным фильтрам
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

      </main>

      {/* Footer */}
      <footer className="bg-slate-900 border-t border-slate-800 py-8 mt-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center text-xs text-slate-500 space-y-2">
          <p className="font-medium text-slate-400">Belstat Crime Dataset Analytics Platform</p>
          <p>Сбор агрегированной официальной статистики преступности с открытого портала Белстат (dataportal.belstat.gov.by)</p>
        </div>
      </footer>
    </div>
  );
}',
  "path": "/home/oddchew/Sundries/work_v3/IPS/belstat_crime_dataset/web_app/src/app/page.tsx",
  "summary": "Full implementation of the refined analytical dashboard UI with interactivity"
}