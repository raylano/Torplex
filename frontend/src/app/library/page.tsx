'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { Filter, Film, Tv, Sparkles, RefreshCw } from 'lucide-react'
import { api, MediaItem, PaginatedResponse } from '@/lib/api'
import MediaCard from '@/components/MediaCard'
import { clsx } from 'clsx'


const typeFilters = [
    { value: '', label: 'All', icon: null },
    { value: 'movie', label: 'Movies', icon: Film },
    { value: 'show', label: 'TV Shows', icon: Tv },
    { value: 'anime_movie,anime_show', label: 'Anime', icon: Sparkles },
]

const stateFilters = [
    { value: '', label: 'All States' },
    { value: 'completed', label: 'Completed' },
    { value: 'requested,indexed,scraped,downloading,downloaded,symlinked', label: 'In Progress' },
    { value: 'failed', label: 'Failed' },
]

export default function LibraryPage() {
    const router = useRouter()
    const [data, setData] = useState<PaginatedResponse<MediaItem> | null>(null)
    const [loading, setLoading] = useState(true)
    const [activeType, setActiveType] = useState('')
    const [activeState, setActiveState] = useState('')
    const [searchQuery, setSearchQuery] = useState('')

    const fetchLibrary = useCallback(async () => {
        setLoading(true)
        try {
            const result = await api.getLibrary({
                page: 1,
                pageSize: 24,
                type: activeType || undefined,
                state: activeState || undefined,
                search: searchQuery || undefined,
            })
            setData(result)
        } catch (error) {
            console.error('Failed to fetch library:', error)
        } finally {
            setLoading(false)
        }
    }, [activeType, activeState, searchQuery])

    useEffect(() => {
        fetchLibrary()
    }, [fetchLibrary])

    return (
        <div className="space-y-6 animate-fade-in">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold gradient-text">Library</h1>
                    <p className="text-gray-400 mt-1">
                        {data?.total || 0} items in your collection
                    </p>
                </div>
                <button
                    onClick={fetchLibrary}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg glass glass-hover transition-all"
                >
                    <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
                    <span>Refresh</span>
                </button>
            </div>

            {/* Filters */}
            <div className="flex flex-wrap items-center gap-4">
                {/* Type filters */}
                <div className="flex items-center gap-2">
                    {typeFilters.map((filter) => (
                        <button
                            key={filter.value}
                            onClick={() => setActiveType(filter.value)}
                            className={clsx(
                                'flex items-center gap-2 px-4 py-2 rounded-lg transition-all',
                                activeType === filter.value
                                    ? 'bg-primary-500/20 text-primary-400 border border-primary-500/30'
                                    : 'glass glass-hover'
                            )}
                        >
                            {filter.icon && <filter.icon size={16} />}
                            <span className="text-sm font-medium">{filter.label}</span>
                        </button>
                    ))}
                </div>

                {/* State filter dropdown */}
                <select
                    value={activeState}
                    onChange={(e) => setActiveState(e.target.value)}
                    className="px-4 py-2 rounded-lg glass border-none bg-white/5 text-sm focus:ring-2 focus:ring-primary-500"
                >
                    {stateFilters.map((filter) => (
                        <option key={filter.value} value={filter.value}>
                            {filter.label}
                        </option>
                    ))}
                </select>

                {/* Search */}
                <input
                    type="text"
                    placeholder="Search library..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="flex-1 max-w-xs px-4 py-2 rounded-lg glass border-none bg-white/5 text-sm placeholder-gray-500 focus:ring-2 focus:ring-primary-500"
                />
            </div>

            {/* Grid */}
            {loading ? (
                <div className="flex items-center justify-center h-64">
                    <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary-500"></div>
                </div>
            ) : data?.items.length ? (
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                    {data.items.map((item) => {
                        const isShow = item.type === 'show' || item.type === 'anime_show'
                        return (
                            <MediaCard
                                key={item.id}
                                item={item}
                                onClick={isShow ? () => router.push(`/show/${item.id}`) : undefined}
                            />
                        )
                    })}
                </div>
            ) : (
                <div className="glass rounded-2xl p-12 text-center">
                    <Filter className="mx-auto text-gray-500 mb-4" size={48} />
                    <p className="text-gray-400">No items found matching your filters.</p>
                </div>
            )}

            {/* Pagination */}
            {data && data.total_pages > 1 && (
                <div className="flex items-center justify-center gap-2">
                    <span className="text-sm text-gray-400">
                        Page {data.page} of {data.total_pages}
                    </span>
                </div>
            )}
        </div>
    )
}
