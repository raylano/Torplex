'use client'

import { useState, useEffect } from 'react'
import Image from 'next/image'
import { Search as SearchIcon, Plus, Film, Tv, Star, TrendingUp, Loader2 } from 'lucide-react'
import { api, SearchResult } from '@/lib/api'
import { clsx } from 'clsx'

export default function SearchPage() {
    const [query, setQuery] = useState('')
    const [results, setResults] = useState<SearchResult[]>([])
    const [trending, setTrending] = useState<SearchResult[]>([])
    const [loading, setLoading] = useState(false)
    const [adding, setAdding] = useState<number | null>(null)
    const [searchType, setSearchType] = useState<'all' | 'movie' | 'tv'>('all')

    // Fetch trending on mount
    useEffect(() => {
        async function fetchTrending() {
            try {
                const data = await api.getTrending()
                setTrending(data.results.slice(0, 12))
            } catch (error) {
                console.error('Failed to fetch trending:', error)
            }
        }
        fetchTrending()
    }, [])

    // Search with debounce
    useEffect(() => {
        if (!query.trim()) {
            setResults([])
            return
        }

        const timer = setTimeout(async () => {
            setLoading(true)
            try {
                const data = await api.search(query, searchType)
                setResults(data)
            } catch (error) {
                console.error('Search failed:', error)
            } finally {
                setLoading(false)
            }
        }, 300)

        return () => clearTimeout(timer)
    }, [query, searchType])

    const handleAdd = async (item: SearchResult) => {
        setAdding(item.id)
        try {
            await api.createMediaItem({
                title: item.title,
                year: item.year || undefined,
                type: item.type === 'tv' ? 'show' : 'movie',
                tmdb_id: item.id,
            })
            // Show success feedback
            alert(`Added "${item.title}" to library!`)
        } catch (error) {
            console.error('Failed to add item:', error)
            alert('Failed to add item. Please try again.')
        } finally {
            setAdding(null)
        }
    }

    const displayItems = query.trim() ? results : trending
    const isShowingTrending = !query.trim()

    return (
        <div className="space-y-6 animate-fade-in">
            {/* Header */}
            <div>
                <h1 className="text-3xl font-bold gradient-text">Search</h1>
                <p className="text-gray-400 mt-1">Find movies and TV shows to add to your library</p>
            </div>

            {/* Search input */}
            <div className="relative">
                <SearchIcon
                    className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400"
                    size={20}
                />
                <input
                    type="text"
                    placeholder="Search for movies or TV shows..."
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    className="w-full pl-12 pr-4 py-4 rounded-xl glass border-none bg-white/5 text-lg placeholder-gray-500 focus:ring-2 focus:ring-primary-500 focus:outline-none"
                />
                {loading && (
                    <Loader2
                        className="absolute right-4 top-1/2 -translate-y-1/2 text-primary-400 animate-spin"
                        size={20}
                    />
                )}
            </div>

            {/* Type filters */}
            <div className="flex items-center gap-2">
                {(['all', 'movie', 'tv'] as const).map((type) => (
                    <button
                        key={type}
                        onClick={() => setSearchType(type)}
                        className={clsx(
                            'px-4 py-2 rounded-lg text-sm font-medium transition-all',
                            searchType === type
                                ? 'bg-primary-500/20 text-primary-400 border border-primary-500/30'
                                : 'glass glass-hover'
                        )}
                    >
                        {type === 'all' ? 'All' : type === 'movie' ? 'Movies' : 'TV Shows'}
                    </button>
                ))}
            </div>

            {/* Section title */}
            {isShowingTrending && displayItems.length > 0 && (
                <div className="flex items-center gap-2 text-gray-400">
                    <TrendingUp size={18} />
                    <span className="text-sm font-medium">Trending This Week</span>
                </div>
            )}

            {/* Results grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                {displayItems.map((item) => (
                    <div
                        key={item.id}
                        className="group relative rounded-xl overflow-hidden glass card-hover"
                    >
                        {/* Poster */}
                        <div className="relative aspect-[2/3] bg-surface-800">
                            {item.poster_url ? (
                                <Image
                                    src={item.poster_url}
                                    alt={item.title}
                                    fill
                                    sizes="(max-width: 768px) 50vw, 16vw"
                                    className="object-cover"
                                />
                            ) : (
                                <div className="absolute inset-0 flex items-center justify-center">
                                    {item.type === 'tv' ? <Tv size={48} className="text-gray-600" /> : <Film size={48} className="text-gray-600" />}
                                </div>
                            )}

                            {/* Overlay */}
                            <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent" />

                            {/* Add button (appears on hover) */}
                            <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/40">
                                <button
                                    onClick={() => handleAdd(item)}
                                    disabled={adding === item.id}
                                    className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary-500 hover:bg-primary-600 text-white font-medium transition-colors disabled:opacity-50"
                                >
                                    {adding === item.id ? (
                                        <Loader2 size={18} className="animate-spin" />
                                    ) : (
                                        <Plus size={18} />
                                    )}
                                    <span>Add</span>
                                </button>
                            </div>

                            {/* Type badge */}
                            <div className="absolute top-2 left-2 flex items-center gap-1 px-2 py-1 rounded-full bg-black/60">
                                {item.type === 'tv' ? <Tv size={12} /> : <Film size={12} />}
                                <span className="text-xs">{item.type === 'tv' ? 'TV' : 'Movie'}</span>
                            </div>

                            {/* Rating */}
                            {item.vote_average && (
                                <div className="absolute top-2 right-2 flex items-center gap-1 px-2 py-1 rounded-lg bg-black/60">
                                    <Star size={12} className="text-yellow-400 fill-yellow-400" />
                                    <span className="text-xs">{item.vote_average.toFixed(1)}</span>
                                </div>
                            )}

                            {/* Title */}
                            <div className="absolute bottom-0 left-0 right-0 p-3">
                                <h3 className="text-sm font-semibold text-white line-clamp-2">
                                    {item.title}
                                </h3>
                                <span className="text-xs text-gray-400">{item.year || 'Unknown'}</span>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Empty state */}
            {query.trim() && !loading && results.length === 0 && (
                <div className="glass rounded-2xl p-12 text-center">
                    <SearchIcon className="mx-auto text-gray-500 mb-4" size={48} />
                    <p className="text-gray-400">No results found for "{query}"</p>
                </div>
            )}
        </div>
    )
}
