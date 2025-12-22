'use client'

import { useState } from 'react'
import { MoreVertical, RefreshCw, Link, FolderOpen, Loader2, HardDrive } from 'lucide-react'

interface RetryDropdownProps {
    itemId: number
    itemType: 'movie' | 'show' | 'episode'
    showId?: number  // For episodes
    onRetryComplete?: () => void
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || ''

export default function RetryDropdown({ itemId, itemType, showId, onRetryComplete }: RetryDropdownProps) {
    const [isOpen, setIsOpen] = useState(false)
    const [loading, setLoading] = useState<string | null>(null)

    const handleRetry = async (mode: string) => {
        setLoading(mode)
        try {
            let url = ''
            if (itemType === 'episode' && showId) {
                url = `${API_URL}/api/library/${showId}/episodes/${itemId}/retry`
            } else if (itemType === 'show' && mode === 'all-episodes') {
                url = `${API_URL}/api/library/${itemId}/retry-all-episodes?mode=failed`
            } else if (itemType === 'show' && mode === 'rescan-mount') {
                url = `${API_URL}/api/library/${itemId}/rescan-mount`
            } else {
                url = `${API_URL}/api/library/${itemId}/retry?mode=${mode}`
            }

            const response = await fetch(url, { method: 'POST' })
            const data = await response.json()

            if (mode === 'rescan-mount' && data.message) {
                alert(data.message)
            }

            onRetryComplete?.()
        } catch (error) {
            console.error('Retry failed:', error)
        } finally {
            setLoading(null)
            setIsOpen(false)
        }
    }

    const menuItems = itemType === 'show'
        ? [
            { key: 'rescan-mount', label: 'Rescan Mount', icon: HardDrive },
            { key: 'all-episodes', label: 'Retry Failed Episodes', icon: RefreshCw },
            { key: 'force', label: 'Force Retry All', icon: RefreshCw },
        ]
        : [
            { key: 'force', label: 'Force Retry', icon: RefreshCw },
            { key: 'symlink', label: 'Retry Symlink', icon: Link },
        ]

    return (
        <div className="relative">
            <button
                onClick={(e) => { e.stopPropagation(); setIsOpen(!isOpen) }}
                className="p-2 rounded-lg hover:bg-white/10 transition-colors"
            >
                <MoreVertical className="w-4 h-4" />
            </button>

            {isOpen && (
                <>
                    <div
                        className="fixed inset-0 z-40"
                        onClick={() => setIsOpen(false)}
                    />
                    <div className="absolute right-0 top-full mt-1 z-50 w-48 py-1 rounded-lg glass border border-white/10 shadow-xl">
                        {menuItems.map((item) => (
                            <button
                                key={item.key}
                                onClick={(e) => { e.stopPropagation(); handleRetry(item.key) }}
                                disabled={loading !== null}
                                className="w-full px-3 py-2 text-left text-sm flex items-center gap-2 hover:bg-white/10 disabled:opacity-50"
                            >
                                {loading === item.key ? (
                                    <Loader2 className="w-4 h-4 animate-spin" />
                                ) : (
                                    <item.icon className="w-4 h-4" />
                                )}
                                {item.label}
                            </button>
                        ))}

                        {itemType !== 'episode' && (
                            <button
                                onClick={(e) => {
                                    e.stopPropagation()
                                    window.open(`/manual-link/${itemId}`, '_blank')
                                }}
                                className="w-full px-3 py-2 text-left text-sm flex items-center gap-2 hover:bg-white/10 border-t border-white/10"
                            >
                                <FolderOpen className="w-4 h-4" />
                                Manual Link...
                            </button>
                        )}
                    </div>
                </>
            )}
        </div>
    )
}
