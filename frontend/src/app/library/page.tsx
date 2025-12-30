'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { Filter, Film, Tv, Sparkles, RefreshCw, ChevronLeft, ChevronRight } from 'lucide-react'
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
    const [page, setPage] = useState(1)
    const [activeType, setActiveType] = useState('')
    const [activeState, setActiveState] = useState('')
    const [searchQuery, setSearchQuery] = useState('')

    const pageSize = 24

    const fetchLibrary = useCallback(async () => {
        setLoading(true)
        try {
            const result = await api.getLibrary({
                page,
                pageSize,
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
    }, [page, activeType, activeState, searchQuery])

    useEffect(() => {
        fetchLibrary()
    }, [fetchLibrary])

    // Reset to page 1 when filters change
    useEffect(() => {
        setPage(1)
    }, [activeType, activeState, searchQuery])

    const goToPage = (newPage: number) => {
        if (newPage >= 1 && newPage <= (data?.total_pages || 1)) {
            setPage(newPage)
            window.scrollTo({ top: 0, behavior: 'smooth' })
        }
    }

    // Generate page numbers to show
    const getPageNumbers = () => {
        if (!data) return []
        const total = data.total_pages
        const current = data.page
        const pages: (number | string)[] = []

        if (total <= 7) {
            for (let i = 1; i <= total; i++) pages.push(i)
        } else {
            if (current <= 3) {
                pages.push(1, 2, 3, 4, '...', total)
            } else if (current >= total - 2) {
                pages.push(1, '...', total - 3, total - 2, total - 1, total)
            } else {
                pages.push(1, '...', current - 1, current, current + 1, '...', total)
            }
        }
        return pages
    }

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
                <div className="flex items-center justify-center gap-2 pt-4">
                    {/* Previous button */}
                    <button
                        onClick={() => goToPage(page - 1)}
                        disabled={page === 1}
                        className={clsx(
                            'flex items-center gap-1 px-3 py-2 rounded-lg transition-all',
                            page === 1
                                ? 'text-gray-600 cursor-not-allowed'
                                : 'glass glass-hover text-gray-300'
                        )}
                    >
                        <ChevronLeft size={18} />
                        <span className="hidden sm:inline">Previous</span>
                    </button>

                    {/* Page numbers */}
                    <div className="flex items-center gap-1">
                        {getPageNumbers().map((pageNum, idx) => (
                            pageNum === '...' ? (
                                <span key={`dots-${idx}`} className="px-2 text-gray-500">...</span>
                            ) : (
                                <button
                                    key={pageNum}
                                    onClick={() => goToPage(pageNum as number)}
                                    className={clsx(
                                        'w-10 h-10 rounded-lg transition-all font-medium',
                                        page === pageNum
                                            ? 'bg-primary-500 text-white'
                                            : 'glass glass-hover text-gray-300'
                                    )}
                                >
                                    {pageNum}
                                </button>
                            )
                        ))}
                    </div>

                    {/* Next button */}
                    <button
                        onClick={() => goToPage(page + 1)}
                        disabled={page === data.total_pages}
                        className={clsx(
                            'flex items-center gap-1 px-3 py-2 rounded-lg transition-all',
                            page === data.total_pages
                                ? 'text-gray-600 cursor-not-allowed'
                                : 'glass glass-hover text-gray-300'
                        )}
                    >
                        <span className="hidden sm:inline">Next</span>
                        <ChevronRight size={18} />
                    </button>
                </div>
            )}
        </div>
    )
}
