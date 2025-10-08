    except Exception as e:
        logger.error(f"Error saving compare set: {e}")
        return JsonResponse({'error': _('Error saving comparison set')}, status=500)
