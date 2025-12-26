using UnityEngine;
using System.Collections;

public class ArtworkClickTracker : MonoBehaviour
{
    [Header("Artwork Info")]
    public string artworkId;
    public string artworkTitle;
    public string artist;
    
    [Header("Tracking")]
    public float minViewTime = 1.0f;
    
    private bool isViewing = false;
    private float viewStartTime;
    private Renderer artworkRenderer;
    private Color originalColor;
    
    void Start()
    {
        artworkRenderer = GetComponent<Renderer>();
        if (artworkRenderer != null)
        {
            originalColor = artworkRenderer.material.color;
        }
        
        // Auto-set ID from name if not set
        if (string.IsNullOrEmpty(artworkId))
        {
            artworkId = gameObject.name;
        }
    }
    
    void OnMouseEnter()
    {
        StartViewing();
        
        // Visual feedback
        if (artworkRenderer != null)
        {
            artworkRenderer.material.color = Color.yellow;
        }
    }
    
    void OnMouseExit()
    {
        StopViewing();
        
        // Reset color
        if (artworkRenderer != null)
        {
            artworkRenderer.material.color = originalColor;
        }
    }
    
    void OnMouseDown()
    {
        // Force stop viewing and record click
        if (isViewing)
        {
            StopViewing(true);
        }
        
        // Trigger AI query about this artwork
        if (AIGuideController.Instance != null)
        {
            AIGuideController.Instance.AskAboutArtwork(artworkTitle);
        }
    }
    
    void StartViewing()
    {
        if (isViewing) return;
        
        isViewing = true;
        viewStartTime = Time.time;
        
        AnalyticsManager.Instance.StartViewingArtwork(artworkId, artworkTitle, artist);
    }
    
    void StopViewing(bool forceStop = false)
    {
        if (!isViewing) return;
        
        float viewDuration = Time.time - viewStartTime;
        
        // Only record if viewed for minimum time or forced
        if (forceStop || viewDuration >= minViewTime)
        {
            AnalyticsManager.Instance.StopViewingArtwork(artworkId, artworkTitle, artist);
        }
        
        isViewing = false;
    }
    
    void OnDestroy()
    {
        // Make sure to stop tracking if object is destroyed
        if (isViewing)
        {
            StopViewing();
        }
    }
}
